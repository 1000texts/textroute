import logging

from sqlalchemy.orm import Session

from src.core.membership_manager import MembershipManager
from src.core.message_manager import MessageManager
from src.core.message_processor import MessageProcessor, ProcessingResult
from src.core.phone_normalize import normalize_phone_number
from src.core.phone_number_manager import PhoneNumberManager
from src.models import Group, Member, Message, PhoneNumber
from src.services.inbound_errors import (
    DuplicateInboundMessageError,
    SenderNotInGroupError,
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
    UnknownSenderError,
)
from src.services.messaging_service import MessagingService

logger = logging.getLogger(__name__)


class InboundMessageService:
    """Coordinates inbound SMS: resolve numbers → persist → process.

    Transaction boundary (intentional):
    1. Resolve + create inbound Message, then ``db.commit()``.
       The original SMS must survive later processor failures.
    2. Process / optional outbound writes, then ``db.commit()`` again.
       On processing failure: ``rollback`` of the *second* unit of work only;
       the inbound Message from step 1 remains durable.

    Managers only ``flush()``; this service owns ``commit`` / ``rollback``.
    """

    def __init__(
        self,
        phone_number_manager: PhoneNumberManager | None = None,
        membership_manager: MembershipManager | None = None,
        message_manager: MessageManager | None = None,
        message_processor: MessageProcessor | None = None,
        messaging_service: MessagingService | None = None,
    ):
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.message_manager = message_manager or MessageManager()
        self.message_processor = message_processor or MessageProcessor()
        self.messaging_service = messaging_service or MessagingService(
            self.message_manager
        )

    def handle_incoming_message(
        self,
        db: Session,
        *,
        from_phone_number: str,
        to_phone_number: str,
        body: str,
        provider_message_id: str | None = None,
    ) -> dict:
        logger.info("inbound_message_received")

        from_phone_number = normalize_phone_number(from_phone_number)
        to_phone_number = normalize_phone_number(to_phone_number)

        if provider_message_id:
            existing = self.message_manager.find_by_provider_message_id(
                db, provider_message_id
            )
            if existing is not None:
                logger.info(
                    "inbound_message_duplicate",
                    extra={"message_id": str(existing.id)},
                )
                raise DuplicateInboundMessageError(str(existing.id))

        receiving_number = self._resolve_receiving_number(db, to_phone_number)
        group = self._resolve_group(receiving_number)
        member = self._resolve_sender(db, from_phone_number)
        self._require_active_membership(db, member, group)

        # Managers flush only; service commits so the inbound row survives
        # processor failure (see class docstring).
        message = self.message_manager.create_inbound(
            db,
            group_id=group.id,
            member_id=member.id,
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
        )
        db.commit()
        logger.info(
            "inbound_message_created",
            extra={"message_id": str(message.id), "group_id": str(group.id)},
        )

        try:
            result = self._process_and_deliver(
                db,
                message=message,
                group=group,
                member=member,
                receiving_number=receiving_number,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "inbound_message_processing_failed",
                extra={"message_id": str(message.id)},
            )
            return {
                "status": "persisted",
                "message_id": str(message.id),
                "processing": "failed",
            }

        return {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "processing": result.notes,
            "response_sent": bool(result.response_body),
        }

    def _resolve_receiving_number(
        self,
        db: Session,
        to_phone_number: str,
    ) -> PhoneNumber:
        phone_number = self.phone_number_manager.find_by_number(db, to_phone_number)
        if phone_number is None:
            logger.warning("unknown_receiving_number")
            raise UnknownReceivingNumberError(
                "Receiving phone number is not configured."
            )
        logger.info(
            "receiving_phone_number_identified",
            extra={"phone_number_id": str(phone_number.id)},
        )
        return phone_number

    def _resolve_group(self, phone_number: PhoneNumber) -> Group:
        if (
            phone_number.group_id is None
            or phone_number.status != "assigned"
            or phone_number.group is None
        ):
            logger.warning(
                "unassigned_receiving_number",
                extra={"phone_number_id": str(phone_number.id)},
            )
            raise UnassignedPhoneNumberError(
                "Receiving phone number is not assigned to a group."
            )
        logger.info(
            "group_identified",
            extra={"group_id": str(phone_number.group_id)},
        )
        return phone_number.group

    def _resolve_sender(self, db: Session, from_phone_number: str) -> Member:
        member = self.membership_manager.get_by_phone(db, from_phone_number)
        if member is None:
            logger.warning("unknown_sender")
            raise UnknownSenderError("Sender is not a known member.")
        logger.info(
            "sender_identified",
            extra={"member_id": str(member.id)},
        )
        return member

    def _require_active_membership(
        self,
        db: Session,
        member: Member,
        group: Group,
    ) -> None:
        membership = self.membership_manager.get_active_membership(
            db,
            member_id=member.id,
            group_id=group.id,
        )
        if membership is None:
            logger.warning(
                "sender_not_in_group",
                extra={
                    "member_id": str(member.id),
                    "group_id": str(group.id),
                },
            )
            raise SenderNotInGroupError("Sender is not an active member of this group.")

    def _process_and_deliver(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
        receiving_number: PhoneNumber,
    ) -> ProcessingResult:
        logger.info(
            "message_processing_started",
            extra={"message_id": str(message.id)},
        )
        result = self.message_processor.process(db, message)
        logger.info(
            "message_processing_completed",
            extra={"message_id": str(message.id)},
        )

        if result.response_body:
            self.messaging_service.send_message(
                db,
                group=group,
                to_member=member,
                from_phone_number=receiving_number.phone_number,
                body=result.response_body,
            )
            logger.info("outbound_message_sent")

        return result
