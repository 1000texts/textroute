"""Inbound SMS use case: resolve context → attach to a request → persist → route.

Entry: ``POST /webhook/messages`` (and ``/webhook/inbound``). A new request is
either queued for a moderator or, when the group's routing policy authorizes it,
routed automatically. Replies are persisted into the request they answer but
never re-routed.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.config.config import Config
from src.core.managers.membership_manager import MembershipManager
from src.core.managers.message_manager import MessageManager
from src.core.managers.request_event_manager import RequestEventManager
from src.core.managers.request_manager import RequestManager
from src.core.processors.message_processor import (
    MessageProcessor,
    ProcessingResult,
    member_context_from_orm,
)
from src.core.phone_normalize import normalize_phone_number
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.core.providers.request_analyzer import RequestAnalysis, RequestAnalyzer
from src.domain.message_role import (
    MessageKind,
    RequestEventType,
    determine_inbound_kind,
    is_routable,
)
from src.domain.message_status import MessageWorkflowStatus
from src.domain.routing_policy import requires_moderation
from src.models import Group, Member, Message, PhoneNumber, Requests
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
    """Coordinates inbound SMS: resolve → attach to a request → persist → route.

    Three separate decisions, deliberately not collapsed into one:
    1. Which request does this belong to? — parentage, decided from explicit
       message records (an open request the sender owns, or one whose fan-out
       copy names them as recipient).
    2. What is this message? — stamped once into ``kind`` at ingress.
    3. How should an ``original_request`` be routed? — the group's policy.

    The second never follows from the first. ``request_id`` is parentage and
    nothing else: every message in a thread carries it, including the original,
    so it cannot say what a message is. Routing asks ``kind`` alone.

    Transaction boundary (intentional):
    1. Resolve, create-or-find the Request, create the inbound Message
       (``received``), then ``db.commit()``. The original SMS must survive later
       processor failures.
    2. Process + store suggestions + policy snapshot, then commit again. On
       processing failure: rollback of the *second* unit of work only, then mark
       the inbound row ``processing_failed`` in a third short commit.
    3. Under ``AUTO_GROUP`` only: authorize routing, commit, then fan out.

    ``MessageProcessor`` only recommends. Fan-out happens here solely when a
    group policy authorizes it — never for replies, and never as approval.
    """

    # The absolute ceiling on a request's life, not the usual way one ends: an
    # idle request is closed after REQUEST_INACTIVITY_AFTER by the same sweep.
    # This bound only catches a request that keeps seeing activity yet never
    # resolves.
    REQUEST_EXPIRES_AFTER = Config.REQUEST_EXPIRES_AFTER

    def __init__(
        self,
        phone_number_manager: PhoneNumberManager | None = None,
        membership_manager: MembershipManager | None = None,
        message_manager: MessageManager | None = None,
        message_processor: MessageProcessor | None = None,
        routing_service: RoutingService | None = None,
        request_manager: RequestManager | None = None,
        request_event_manager: RequestEventManager | None = None,
        request_analyzer: RequestAnalyzer | None = None,
    ):
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.message_manager = message_manager or MessageManager()
        self.message_processor = message_processor or MessageProcessor()
        self.request_manager = request_manager or RequestManager()
        self.request_event_manager = request_event_manager or RequestEventManager()
        self.request_analyzer = request_analyzer or RequestAnalyzer()
        self.routing_service = routing_service or RoutingService(
            message_manager=self.message_manager,
            phone_number_manager=self.phone_number_manager,
            request_event_manager=self.request_event_manager,
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

        # Step 1 of 3: which request does this belong to? Parentage only. Both
        # lookups read explicit message records — an open request this member
        # owns, or one whose fan-out copy names them as its recipient — so the
        # answer never depends on a clock.
        existing_request = self._find_open_request(db, group=group, member=member)

        # Step 2 of 3: decide what this message *is*, once, here. Everything
        # downstream reads the stamped column rather than working it out again.
        kind = determine_inbound_kind(joins_open_request=existing_request is not None)

        request = existing_request or self.request_manager.create(
            db,
            group_id=group.id,
            requester_id=member.id,
            expires_at=datetime.now(timezone.utc) + self.REQUEST_EXPIRES_AFTER,
        )

        # A reply hangs off the request's original message, keeping the star
        # topology. The edge is now redundant for threading, which request_id
        # owns, but it remains the message graph.
        parent_message_id = (
            request.original_message_id if existing_request is not None else None
        )

        try:
            message = self.message_manager.create_inbound(
                db,
                group_id=group.id,
                member_id=member.id,
                kind=kind,
                request_id=request.id,
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

        if existing_request is None:
            # Deferred FK: the two rows point at each other, so the request's
            # original message can only be named once the message exists.
            self.request_manager.set_original_message(db, request, message.id)

        db.commit()
        logger.info(
            "inbound_message_created",
            extra={
                "message_id": str(message.id),
                "group_id": str(group.id),
                "request_id": request.id,
                "kind": kind.value,
            },
        )

        # Dispatch on the stamped kind through the one predicate that decides
        # what a routing policy may act on. Anything not routable is recorded
        # into its request and left alone.
        if not is_routable(kind):
            return self._handle_member_reply(
                db, message=message, group=group, member=member, request=request
            )
        return self._handle_new_request(
            db, message=message, group=group, member=member, request=request
        )

    def _find_open_request(
        self,
        db: Session,
        *,
        group: Group,
        member: Member,
    ) -> Requests | None:
        """The live request this message belongs to, if any.

        Two explicit lookups, in order: the sender's own open request (their
        follow-up), then any open request whose fan-out copy was addressed to
        them (their answer to someone else's). Both read message rows and
        columns, which is what replaced the old two-hour timing window: a
        request's lifecycle now says how long it can gather replies.
        """
        own = self.request_manager.find_open_for_requester(
            db,
            group_id=group.id,
            requester_id=member.id,
        )
        if own is not None:
            return own
        return self.request_manager.find_open_for_participant(
            db,
            group_id=group.id,
            member_id=member.id,
        )

    def _handle_member_reply(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
        request: Requests,
    ) -> dict:
        """Record a reply into its request; do not re-route it.

        Replies bypass moderation as a **slice-level product policy**, not
        because they belong to a request. Being a reply does not mean "no
        moderator ever needs to see this" — it means TextRoute does not re-route
        replies yet. A future reply-intent analyzer may find a new request
        inside one; today "I have one. Also, anyone have a pressure washer?" is
        handled only as a reply.

        The group routing policy is deliberately not consulted here, so
        ``AUTO_GROUP`` can never broadcast a reply to the whole group.
        """
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.RECEIVED.value,
            processing_notes="reply_recorded_unprocessed",
        )
        db.commit()
        return {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "request_id": request.id,
            "kind": MessageKind.MEMBER_REPLY.value,
            "workflow_status": message.workflow_status,
            "processing": "reply_recorded",
            "parent_message_id": (
                str(message.parent_message_id) if message.parent_message_id else None
            ),
        }

    def _handle_new_request(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
        request: Requests,
    ) -> dict:
        """Analyze the request, then route per the group's policy."""
        try:
            result = self._process_for_moderation(
                db,
                message=message,
                group=group,
                member=member,
                request=request,
            )
            # Step 3 of 3: how should this new request be routed? Snapshot the
            # policy in force so later policy changes cannot rewrite history.
            self.message_manager.record_routing_policy(
                db,
                message,
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
                "request_id": request.id,
                "kind": MessageKind.ORIGINAL_REQUEST.value,
                "processing": "failed",
                "workflow_status": MessageWorkflowStatus.PROCESSING_FAILED.value,
            }

        response = {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "request_id": request.id,
            "kind": MessageKind.ORIGINAL_REQUEST.value,
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
            request=request,
            suggested_recipient_ids=result.suggested_recipient_ids,
            response=response,
        )

    def _authorize_automatic_routing(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        request: Requests,
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
        self.request_event_manager.record(
            db,
            request_id=request.id,
            event_type=RequestEventType.AUTHORIZED,
            message_id=message.id,
            payload={
                "by": "policy_auto_group",
                "recipient_ids": [str(m.id) for m in recipients],
            },
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
        request: Requests,
    ) -> ProcessingResult:
        """Suggestions only — moderator still chooses recipients."""
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

        # Describe the request on the request itself. Recipients come from the
        # processor above; the analyzer only says what is being asked for, and
        # falls back to those same keyword results when the model is unavailable.
        analysis = self.request_analyzer.analyze(
            message.body,
            fallback=RequestAnalysis(
                request_type=result.intent,
                summary=message.body[:140],
                extracted_filters=result.constraints or {},
                confidence=result.confidence,
                notes="keyword_fallback",
            ),
        )
        self.request_manager.apply_analysis(
            db,
            request,
            request_type=analysis.request_type,
            extracted_filters=analysis.extracted_filters,
            summary=analysis.summary,
            embedding=analysis.embedding,
            model_name=analysis.model_name,
            confidence=analysis.confidence,
        )

        # The message records the analysis that drove *this* routing decision,
        # while the request carries the current best understanding. They can
        # diverge if a request is re-analyzed, which is the point of keeping
        # both.
        self.message_manager.apply_processing_result(
            db,
            message,
            intent=analysis.request_type,
            constraints=analysis.extracted_filters or None,
            confidence=analysis.confidence,
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
