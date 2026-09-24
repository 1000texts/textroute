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
from src.core.providers.request_analyzer import RequestAnalyzer
from src.domain.association import (
    CHOICE_RECEIVED,
    CHOICE_UNRECOGNIZED,
    NEW_REQUEST_LABEL,
    NEW_REQUEST_LETTER,
    candidate_label,
    choice_letters,
    clarification_question,
    cosine_similarity,
    leading_request,
    parse_choice,
)
from src.domain.intent_status import REPLY_DEFERRED, REPLY_RECORDED, intent_blocks_reply
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
        embed_text=None,
    ):
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.message_manager = message_manager or MessageManager()
        self.message_processor = message_processor or MessageProcessor()
        self.request_manager = request_manager or RequestManager()
        self.request_event_manager = request_event_manager or RequestEventManager()
        self.request_analyzer = request_analyzer or RequestAnalyzer()
        # None means the Ollama embeddings in src.ai.llm. Tests pass a function.
        self.embed_text = embed_text
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

        # A letter answering a question we already asked is not a new text.
        pending = self.message_manager.find_pending_clarification(
            db, group_id=group.id, member_id=member.id
        )
        choices = _clarification_choices(pending)
        if choices is not None:
            return self._handle_choice(
                db,
                pending=pending,
                choices=choices,
                group=group,
                member=member,
                body=body,
                from_phone_number=from_phone_number,
                to_phone_number=to_phone_number,
                provider_message_id=provider_message_id,
            )

        # Which open requests could this text be answering? Own request, plus
        # every open request whose fan-out copy names them. One is a reply.
        # None is a new request. Two or more are weighed.
        candidates = self._candidate_requests(db, group=group, member=member)
        if len(candidates) >= 2:
            winner_id = self._weigh(db, body, candidates)
            if winner_id is None:
                return self._ask_which_request(
                    db,
                    group=group,
                    member=member,
                    candidates=candidates,
                    body=body,
                    from_phone_number=from_phone_number,
                    to_phone_number=to_phone_number,
                    provider_message_id=provider_message_id,
                )
            existing_request = next(
                request for request in candidates if request.id == winner_id
            )
        elif len(candidates) == 1:
            existing_request = candidates[0]
        else:
            existing_request = None

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
            logger.info(
                "reply_received",
                extra={
                    "message_id": str(message.id),
                    "request_id": request.id,
                    "parent_message_id": (
                        str(message.parent_message_id)
                        if message.parent_message_id
                        else None
                    ),
                },
            )
            if intent_blocks_reply(getattr(request, "intent_status", None)):
                return self._defer_reply(
                    db, message=message, group=group, member=member, request=request
                )
            return self._handle_member_reply(
                db, message=message, group=group, member=member, request=request
            )
        return self._handle_new_request(
            db, message=message, group=group, member=member, request=request
        )

    def _candidate_requests(
        self,
        db: Session,
        *,
        group: Group,
        member: Member,
    ) -> list[Requests]:
        """Open requests this sender could be answering, own request first."""
        own = self.request_manager.find_open_for_requester(
            db,
            group_id=group.id,
            requester_id=member.id,
        )
        found = self.request_manager.find_open_for_participant(
            db,
            group_id=group.id,
            member_id=member.id,
        )
        if found is None:
            others: list[Requests] = []
        elif isinstance(found, list):
            others = found
        else:
            others = [found]

        candidates: list[Requests] = []
        if own is not None:
            candidates.append(own)
        own_id = getattr(own, "id", None)
        for request in others:
            if request.id != own_id:
                candidates.append(request)
        return candidates

    def _weigh(
        self,
        db: Session,
        body: str,
        candidates: list[Requests],
    ) -> int | None:
        """Request id that clearly associates, or None when the scores are low.

        An embedding failure is low confidence: ask, do not guess, do not drop
        the SMS.
        """
        try:
            inbound_vector = self._embed(body)
            scores: list[tuple[int, float]] = []
            for request in candidates:
                scores.append(
                    (
                        request.id,
                        cosine_similarity(
                            inbound_vector,
                            self._embed(self._candidate_text(db, request)),
                        ),
                    )
                )
        except Exception:
            logger.exception("association_embed_failed")
            return None
        return leading_request(scores)

    def _embed(self, text: str) -> list[float]:
        if self.embed_text is not None:
            return list(self.embed_text(text))
        # Imported here so a path that never weighs does not load Ollama.
        from src.ai.llm import EMBEDDINGS

        return list(EMBEDDINGS.embed_query(text))

    def _candidate_text(self, db: Session, request: Requests) -> str:
        summary = getattr(request, "summary", None)
        original_body = None
        original_id = getattr(request, "original_message_id", None)
        if original_id is not None:
            original = self.message_manager.find_by_id(db, original_id)
            if original is not None:
                original_body = original.body
        return candidate_label(
            summary=summary,
            original_body=original_body,
            request_id=request.id,
        )

    def _ask_which_request(
        self,
        db: Session,
        *,
        group: Group,
        member: Member,
        candidates: list[Requests],
        body: str,
        from_phone_number: str,
        to_phone_number: str,
        provider_message_id: str | None,
    ) -> dict:
        """Store the text unstamped and ask which request it belongs to."""
        has_own = any(
            getattr(request, "requester_id", None) == member.id
            for request in candidates
        )
        letters = choice_letters(len(candidates))
        options: list[tuple[str, str]] = []
        choices: dict = {}
        for letter, request in zip(letters, candidates):
            label = self._candidate_text(db, request)
            options.append((letter, label))
            choices[letter] = {"request_id": request.id, "label": label}
        if not has_own:
            options.append((NEW_REQUEST_LETTER, NEW_REQUEST_LABEL))
            choices[NEW_REQUEST_LETTER] = {
                "request_id": None,
                "label": NEW_REQUEST_LABEL,
            }
        question = clarification_question(options)
        message = self.message_manager.create_pending_choice(
            db,
            group_id=group.id,
            member_id=member.id,
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            choices=choices,
        )
        db.commit()
        self._send_question(db, group=group, member=member, question=question)
        return {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "request_id": None,
            "kind": None,
            "processing": "clarification_requested",
        }

    def _send_question(
        self,
        db: Session,
        *,
        group: Group,
        member: Member,
        question: str,
    ) -> None:
        try:
            from_number = self.routing_service.resolve_from_number(db, group)
            self.routing_service.messaging_service.send_message(
                db,
                group=group,
                to_member=member,
                from_phone_number=from_number,
                body=question,
                kind=MessageKind.FANOUT_COPY,
                sender_name=None,
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "clarification_send_failed",
                extra={"group_id": str(group.id), "member_id": str(member.id)},
            )

    def _handle_choice(
        self,
        db: Session,
        *,
        pending: Message,
        choices: dict,
        group: Group,
        member: Member,
        body: str,
        from_phone_number: str,
        to_phone_number: str,
        provider_message_id: str | None,
    ) -> dict:
        letter = parse_choice(body, set(choices))
        if letter is None:
            self.message_manager.record_choice_text(
                db,
                group_id=group.id,
                member_id=member.id,
                from_phone_number=from_phone_number,
                to_phone_number=to_phone_number,
                body=body,
                provider_message_id=provider_message_id,
                note=CHOICE_UNRECOGNIZED,
            )
            db.commit()
            question = clarification_question(
                [
                    (key, value["label"])
                    for key, value in choices.items()
                    if isinstance(value, dict) and value.get("label")
                ]
            )
            self._send_question(db, group=group, member=member, question=question)
            return {
                "status": "ok",
                "message_id": str(pending.id),
                "request_id": None,
                "kind": None,
                "processing": "clarification_requested",
            }

        self.message_manager.record_choice_text(
            db,
            group_id=group.id,
            member_id=member.id,
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            note=CHOICE_RECEIVED,
        )
        selected = choices[letter]
        request_id = selected.get("request_id") if isinstance(selected, dict) else None
        if request_id is None:
            request = self.request_manager.create(
                db,
                group_id=group.id,
                requester_id=member.id,
                expires_at=datetime.now(timezone.utc) + self.REQUEST_EXPIRES_AFTER,
            )
            self.message_manager.attach_held_message(
                db,
                pending,
                kind=MessageKind.ORIGINAL_REQUEST,
                member_id=member.id,
                request_id=request.id,
                parent_message_id=None,
            )
            self.request_manager.set_original_message(db, request, pending.id)
            db.commit()
            return self._handle_new_request(
                db, message=pending, group=group, member=member, request=request
            )

        request = self.request_manager.find_by_id(db, request_id)
        parent_id = getattr(request, "original_message_id", None) if request else None
        self.message_manager.attach_held_message(
            db,
            pending,
            kind=MessageKind.MEMBER_REPLY,
            member_id=member.id,
            request_id=request_id,
            parent_message_id=parent_id,
        )
        db.commit()
        return self._handle_member_reply(
            db, message=pending, group=group, member=member, request=request
        )

    def _defer_reply(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
        request: Requests,
    ) -> dict:
        """Keep the reply on its request until intent is committed."""
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.RECEIVED.value,
            processing_notes=REPLY_DEFERRED,
        )
        db.commit()
        logger.info(
            "reply_deferred_waiting_for_intent",
            extra={
                "message_id": str(message.id),
                "request_id": request.id,
                "parent_message_id": (
                    str(message.parent_message_id) if message.parent_message_id else None
                ),
            },
        )
        return {
            "status": "ok",
            "message_id": str(message.id),
            "group_id": str(group.id),
            "member_id": str(member.id),
            "request_id": request.id,
            "kind": MessageKind.MEMBER_REPLY.value,
            "processing": "reply_deferred",
            "parent_message_id": (
                str(message.parent_message_id) if message.parent_message_id else None
            ),
        }

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
        if getattr(message, "processing_notes", None) == REPLY_RECORDED:
            return {
                "status": "ok",
                "message_id": str(message.id),
                "group_id": str(group.id),
                "member_id": str(member.id),
                "request_id": request.id,
                "kind": MessageKind.MEMBER_REPLY.value,
                "processing": "reply_recorded",
                "parent_message_id": (
                    str(message.parent_message_id) if message.parent_message_id else None
                ),
            }
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.RECEIVED.value,
            processing_notes=REPLY_RECORDED,
        )
        message.processing_notes = REPLY_RECORDED
        db.commit()
        logger.info(
            "reply_processed",
            extra={"message_id": str(message.id), "request_id": request.id},
        )
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
                "discover_intent": True,
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
            "discover_intent": True,
        }

        if requires_moderation(group.routing_policy):
            return response

        return self._authorize_automatic_routing(
            db,
            message=message,
            group=group,
            member=member,
            request=request,
            response=response,
        )

    def _authorize_automatic_routing(
        self,
        db: Session,
        *,
        message: Message,
        group: Group,
        member: Member,
        request: Requests,
        response: dict,
    ) -> dict:
        """The group's policy authorizes routing — no moderator approved this.

        Recipients are every other active member. That set does not come from
        the processor's suggestions or from intent. Status is
        ``auto_authorized``, never ``approved``: the stored row must not imply
        a human reviewed the message.
        """
        recipients = self._other_active_members(
            db, group_id=group.id, sender_id=member.id
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
        logger.info(
            "original_fanned_out",
            extra={
                "message_id": str(message.id),
                "request_id": request.id,
                "recipient_count": len(recipients),
            },
        )
        response["workflow_status"] = message.workflow_status
        response["processing"] = "auto_group_authorized"
        response.update(delivery)
        return response

    def _other_active_members(self, db: Session, *, group_id, sender_id) -> list[Member]:
        """Every active member of the group except the sender."""
        recipients: list[Member] = []
        for membership in self.membership_manager.list_active_memberships(db, group_id):
            person = getattr(membership, "member", None)
            if person is None or person.id == sender_id:
                continue
            recipients.append(person)
        return recipients

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

        # Keyword snapshot for the routing decision only. The request's intent
        # is written later, off this request, by IntentService.
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


def _clarification_choices(pending) -> dict | None:
    """The letter map on a held message, or None when this row is not one.

    A bare mock has no real ``constraints`` dict, so existing tests that do
    not set up a pending question fall through to normal ingress.
    """
    if pending is None:
        return None
    constraints = getattr(pending, "constraints", None)
    if not isinstance(constraints, dict):
        return None
    choices = constraints.get("clarification")
    if not isinstance(choices, dict) or not choices:
        return None
    return choices
