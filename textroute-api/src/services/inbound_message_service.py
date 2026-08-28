"""Inbound SMS use case: resolve context → durable persist → determine kind → route.

Entry: ``POST /webhook/messages`` (and ``/webhook/inbound``). A new request is
either queued for a moderator or, when the group's routing policy authorizes it,
routed automatically. Replies are persisted and linked but never re-routed.
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.managers.membership_manager import MembershipManager
from src.core.managers.message_manager import MessageManager
from src.core.processors.message_processor import (
    MessageProcessor,
    ProcessingResult,
    member_context_from_orm,
)
from src.core.phone_normalize import normalize_phone_number
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.domain.message_kind import InboundMessageKind, determine_inbound_kind
from src.domain.message_status import MessageWorkflowStatus
from src.domain.routing_policy import requires_moderation
from src.models import Group, Member, Message, PhoneNumber
from src.services.routing_service import RoutingService
from src.services.inbound_errors import (
    DuplicateInboundMessageError,
    SenderNotInGroupError,
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
    UnknownSenderError,
)

logger = logging.getLogger(__name__)


class InboundMessageService:
    """Coordinates inbound SMS: resolve → persist → determine kind → route.

    Three separate decisions, deliberately not collapsed into one:
    1. Is there an original request *candidate*? (timing) — sets the relationship.
    2. What kind of inbound message is this? — selects the workflow.
    3. How should a NEW_REQUEST be routed? — the group's routing policy.

    ``parent_message_id`` represents message relationship, not moderation state.
    A non-null parent does not by itself exempt a message from moderation.

    Transaction boundary (intentional):
    1. Resolve + create inbound Message (``received``), then ``db.commit()``.
       The original SMS must survive later processor failures.
    2. Process + store suggestions + kind/policy snapshot, then commit again.
       On processing failure: rollback of the *second* unit of work only, then
       mark the inbound row ``processing_failed`` in a third short commit.
    3. Under ``AUTO_GROUP`` only: authorize routing, commit, then fan out.

    ``MessageProcessor`` only recommends. Fan-out happens here solely when a
    group policy authorizes it — never for replies, and never as approval.
    """

    # How recently a member must have received a request for it to count as a
    # candidate for their next inbound. Kept short on purpose: the longer the
    # window, the more unrelated new requests get mislabelled as replies.
    ORIGINAL_REQUEST_CANDIDATE_WINDOW_HOURS = 2

    def __init__(
        self,
        phone_number_manager: PhoneNumberManager | None = None,
        membership_manager: MembershipManager | None = None,
        message_manager: MessageManager | None = None,
        message_processor: MessageProcessor | None = None,
        routing_service: RoutingService | None = None,
    ):
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.message_manager = message_manager or MessageManager()
        self.message_processor = message_processor or MessageProcessor()
        self.routing_service = routing_service or RoutingService(
            message_manager=self.message_manager,
            phone_number_manager=self.phone_number_manager,
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

        receiving_number = self._resolve_receiving_number(
            db, to_phone_number
        )  # if receiving number is not configured, raise an error
        group = self._resolve_group(
            receiving_number
        )  # if receiving number is not assigned to a group, raise an error
        member = self._resolve_sender(
            db, from_phone_number
        )  # if sender is not a known member, raise an error
        self._require_active_membership(
            db, member, group
        )  # if member is not active, raise an error

        # Step 1 of 3: which original request did this member recently receive?
        # This sets the *relationship* only — it decides nothing about
        # moderation, and it does not yet claim the new message is a reply.
        #
        # The candidate is the original request itself, not the per-recipient
        # fan-out copy, so every reply hangs off the one request (a star, not a
        # chain of copies).
        parent_message_id = None
        original_request_candidate = (
            self.message_manager.find_original_request_candidate_for_member(
                db,
                group_id=group.id,
                member_id=member.id,
                within_hours=self.ORIGINAL_REQUEST_CANDIDATE_WINDOW_HOURS,
            )
        )
        if original_request_candidate is not None:
            parent_message_id = original_request_candidate.id

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

        # Step 2 of 3: decide what this message *is*. Dispatch on kind, never on
        # `parent_message_id` — a relationship is not a moderation decision.
        kind = determine_inbound_kind(
            has_original_request_candidate=original_request_candidate is not None
        )
        if kind is InboundMessageKind.REPLY:
            return self._handle_reply(db, message=message, group=group, member=member)
        return self._handle_new_request(
            db, message=message, group=group, member=member
        )

    def _handle_reply(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
    ) -> dict:
        """Persist and link a reply; do not re-route it.

        Replies bypass moderation as a **slice-level product policy**, not because
        ``parent_message_id`` is set. Being a reply does not mean "no moderator
        ever needs to see this" — it means TextRoute does not re-route replies
        yet. Future reply analysis may classify a message as ``REPLY``,
        ``NEW_REQUEST``, or ``REPLY_WITH_NEW_REQUEST``; today "I have one. Also,
        anyone have a pressure washer?" is handled only as the former.

        The group routing policy is deliberately *not* consulted here, so
        ``AUTO_GROUP`` can never broadcast a reply to the whole group.
        """
        self.message_manager.record_routing_context(
            db,
            message,
            kind=InboundMessageKind.REPLY.value,
        )
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.RECEIVED.value,
            processing_notes="possible_reply_persisted_unprocessed",
        )
        db.commit()
        return {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "kind": InboundMessageKind.REPLY.value,
            "workflow_status": message.workflow_status,
            "processing": "possible_reply_persisted",
            "parent_message_id": str(message.parent_message_id),
        }

    def _handle_new_request(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
    ) -> dict:
        """Classify, then route per the group's policy."""
        try:
            result = self._process_for_moderation(
                db,
                message=message,
                group=group,
                member=member,
            )
            # Step 3 of 3: how should this new request be routed? Snapshot the
            # policy in force so later policy changes cannot rewrite history.
            self.message_manager.record_routing_context(
                db,
                message,
                kind=InboundMessageKind.NEW_REQUEST.value,
                routing_policy=group.routing_policy,
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
                "kind": InboundMessageKind.NEW_REQUEST.value,
                "processing": "failed",
                "workflow_status": MessageWorkflowStatus.PROCESSING_FAILED.value,
            }

        response = {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "kind": InboundMessageKind.NEW_REQUEST.value,
            "routing_policy": group.routing_policy,
            "workflow_status": message.workflow_status,
            "intent": result.intent,
            "suggested_recipient_count": len(result.suggested_recipient_ids),
            "processing": result.notes,
        }

        if requires_moderation(group.routing_policy):
            return response

        return self._authorize_automatic_routing(
            db,
            message=message,
            group=group,
            suggested_recipient_ids=result.suggested_recipient_ids,
            response=response,
        )

    def _authorize_automatic_routing(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        suggested_recipient_ids: list,
        response: dict,
    ) -> dict:
        """The group's policy authorizes routing — no moderator approved this.

        Status is ``auto_authorized``, never ``approved``: the stored row must
        not imply a human reviewed the message.
        """
        recipients = self._load_active_recipients(
            db,
            group_id=group.id,
            recipient_ids=suggested_recipient_ids,
        )
        if not recipients:
            # Nobody to route to (e.g. single-member group). Leave it for a
            # moderator rather than recording a delivery to no one.
            logger.info(
                "auto_routing_skipped_no_recipients",
                extra={"message_id": str(message.id)},
            )
            response["processing"] = "auto_routing_skipped_no_recipients"
            return response

        self.message_manager.apply_routing_authorization(
            db,
            message,
            routed_recipient_ids=[m.id for m in recipients],
        )
        db.commit()

        delivery = self.routing_service.fan_out(db, message, recipients)
        response["workflow_status"] = message.workflow_status
        response["processing"] = "auto_group_authorized"
        response.update(delivery)
        return response

    def _load_active_recipients(
        self,
        db: Session,
        *,
        group_id,
        recipient_ids: list,
    ) -> list[Member]:
        """Skip anyone whose membership lapsed between suggestion and send."""
        recipients: list[Member] = []
        for member_id in recipient_ids:
            membership = self.membership_manager.get_active_membership(
                db,
                member_id=member_id,
                group_id=group_id,
            )
            if membership is not None and membership.member is not None:
                recipients.append(membership.member)
        return recipients

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
