"""Inbound SMS use case: resolve context → durable persist → suggest → queue.

Entry: ``POST /webhook/messages`` (and ``/webhook/inbound``). This path never
sends SMS; delivery happens only after moderator approval.
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.membership_manager import MembershipManager
from src.core.message_manager import MessageManager
from src.core.message_processor import (
    MessageProcessor,
    ProcessingResult,
    member_context_from_orm,
)
from src.core.phone_normalize import normalize_phone_number
from src.core.phone_number_manager import PhoneNumberManager
from src.domain.message_status import MessageWorkflowStatus
from src.models import Group, Member, Message, PhoneNumber
from src.services.inbound_errors import (
    DuplicateInboundMessageError,
    SenderNotInGroupError,
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
    UnknownSenderError,
)

logger = logging.getLogger(__name__)


class InboundMessageService:
    """Coordinates inbound SMS: resolve → persist → classify → await moderator.

    Transaction boundary (intentional):
    1. Resolve + create inbound Message (``received``), then ``db.commit()``.
       The original SMS must survive later processor failures.
    2. Process + store suggestions (``awaiting_moderator``), then commit again.
       On processing failure: rollback of the *second* unit of work only, then
       mark the inbound row ``processing_failed`` in a third short commit.

    ``MessageProcessor`` only recommends. This service never fan-outs SMS.
    """

    def __init__(
        self,
        phone_number_manager: PhoneNumberManager | None = None,
        membership_manager: MembershipManager | None = None,
        message_manager: MessageManager | None = None,
        message_processor: MessageProcessor | None = None,
    ):
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.message_manager = message_manager or MessageManager()
        self.message_processor = message_processor or MessageProcessor()

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

        # Idempotency: provider retries must not create duplicate rows.
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

        # Link replies to the originating inbound when this member was recently
        # fan-out'd. Reply intelligence is deferred; we only persist + link.
        parent_message_id = None
        recent_fanout = self.message_manager.find_recent_fanout_to_member(
            db,
            group_id=group.id,
            member_id=member.id,
        )
        if recent_fanout is not None:
            parent_message_id = recent_fanout.parent_message_id

        try:
            message = self.message_manager.create_inbound(
                db,
                group_id=group.id,
                member_id=member.id,
                from_phone_number=from_phone_number,
                to_phone_number=to_phone_number,
                body=body,
                provider_message_id=provider_message_id,
                parent_message_id=parent_message_id,
                workflow_status=MessageWorkflowStatus.RECEIVED.value,
            )
        except IntegrityError:
            # Pre-insert lookup is a fast path; UNIQUE is authoritative under races.
            db.rollback()
            existing = (
                self.message_manager.find_by_provider_message_id(
                    db, provider_message_id
                )
                if provider_message_id
                else None
            )
            if existing is None:
                raise
            logger.info(
                "inbound_message_duplicate_after_insert_race",
                extra={"message_id": str(existing.id)},
            )
            raise DuplicateInboundMessageError(str(existing.id)) from None
        db.commit()
        logger.info(
            "inbound_message_created",
            extra={"message_id": str(message.id), "group_id": str(group.id)},
        )

        # Vertical slice: persist replies without classification yet.
        if parent_message_id is not None:
            self.message_manager.set_workflow_status(
                db,
                message,
                MessageWorkflowStatus.RECEIVED.value,
                processing_notes="reply_persisted_unprocessed",
            )
            db.commit()
            return {
                "status": "ok",
                "message_id": str(message.id),
                "group_id": str(group.id),
                "member_id": str(member.id),
                "workflow_status": message.workflow_status,
                "processing": "reply_persisted",
                "parent_message_id": str(parent_message_id),
            }

        try:
            result = self._process_for_moderation(
                db,
                message=message,
                group=group,
                member=member,
            )
            db.commit()
        except Exception:
            message_id = message.id
            db.rollback()
            logger.exception(
                "inbound_message_processing_failed",
                extra={"message_id": str(message_id)},
            )
            # Fresh transaction: mark durable inbound as failed without losing it.
            failed = self.message_manager.find_by_id(db, message_id)
            if failed is not None:
                self.message_manager.set_workflow_status(
                    db,
                    failed,
                    MessageWorkflowStatus.PROCESSING_FAILED.value,
                    processing_notes="processor_exception",
                )
                db.commit()
            return {
                "status": "persisted",
                "message_id": str(message_id),
                "processing": "failed",
                "workflow_status": MessageWorkflowStatus.PROCESSING_FAILED.value,
            }

        return {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "workflow_status": message.workflow_status,
            "intent": result.intent,
            "suggested_recipient_count": len(result.suggested_recipient_ids),
            "processing": result.notes,
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

    def _process_for_moderation(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
    ) -> ProcessingResult:
        """Heuristic suggestions only — moderator still chooses recipients."""
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.PROCESSING.value,
        )
        logger.info(
            "message_processing_started",
            extra={"message_id": str(message.id)},
        )

        memberships = self.membership_manager.list_active_memberships(db, group.id)
        candidates = [
            member_context_from_orm(m.member, role=m.role)
            for m in memberships
            if m.member is not None
        ]

        result = self.message_processor.process(
            message_body=message.body,
            sender_id=member.id,
            candidates=candidates,
        )

        self.message_manager.apply_processing_result(
            db,
            message,
            intent=result.intent,
            constraints=result.constraints or None,
            confidence=result.confidence,
            suggested_recipient_ids=result.suggested_recipient_ids,
            notes=result.notes,
            workflow_status=MessageWorkflowStatus.AWAITING_MODERATOR.value,
        )
        logger.info(
            "message_processing_completed",
            extra={
                "message_id": str(message.id),
                "workflow_status": message.workflow_status,
            },
        )
        return result
