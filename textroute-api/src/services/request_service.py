"""The request lifecycle: read a thread, speak into it, and close it.

Callers (routes) pass ``group_id`` from the authenticated session. This service
scopes every lookup to that group; it does not authenticate.

Owns transactions: managers flush, this commits.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.config.config import Config
from src.core.managers.membership_manager import MembershipManager
from src.core.managers.message_manager import MessageManager
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.core.managers.request_event_manager import RequestEventManager
from src.core.managers.request_manager import RequestManager
from src.core.providers.sms_provider import SmsProviderError
from src.domain.message_role import MessageKind, RequestEventType
from src.models import Member, Message, Requests
from src.services.messaging_service import MessagingService
from src.services.routing_service import RoutingError, RoutingService

logger = logging.getLogger(__name__)


class RequestError(Exception):
    """Base request lifecycle error."""


class RequestNotFoundError(RequestError):
    pass


class RequestNotOpenError(RequestError):
    pass


class NoRecipientsError(RequestError):
    pass


class RequestService:

    def __init__(
        self,
        request_manager: RequestManager | None = None,
        request_event_manager: RequestEventManager | None = None,
        message_manager: MessageManager | None = None,
        membership_manager: MembershipManager | None = None,
        phone_number_manager: PhoneNumberManager | None = None,
        messaging_service: MessagingService | None = None,
        routing_service: RoutingService | None = None,
    ):
        self.request_manager = request_manager or RequestManager()
        self.request_event_manager = request_event_manager or RequestEventManager()
        self.message_manager = message_manager or MessageManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.messaging_service = messaging_service or MessagingService(
            self.message_manager
        )
        self.routing_service = routing_service or RoutingService(
            message_manager=self.message_manager,
            phone_number_manager=self.phone_number_manager,
            request_event_manager=self.request_event_manager,
        )

    # -- reading ------------------------------------------------------------

    def list_requests(
        self,
        db: Session,
        group_id: UUID,
        *,
        statuses: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict]:
        requests = self.request_manager.list_for_group(
            db,
            group_id=group_id,
            statuses=statuses,
            limit=limit,
        )
        # One rollup query for the whole page rather than one per row.
        rollups = self.request_manager.summarize_activity(
            db,
            request_ids=[r.id for r in requests],
        )
        return [self._summary(db, r, rollups.get(r.id)) for r in requests]

    def get_request(self, db: Session, request_id: int, *, group_id: UUID) -> dict:
        """One request with its whole conversation and audit trail."""
        request = self._require_request(db, request_id, group_id)
        rollups = self.request_manager.summarize_activity(
            db,
            request_ids=[request.id],
        )
        detail = self._summary(db, request, rollups.get(request.id))
        detail["messages"] = [
            self._message_brief(db, m)
            for m in self.request_manager.load_thread(db, request.id)
        ]
        detail["events"] = [
            {
                "id": e.id,
                "event_type": e.event_type,
                "message_id": str(e.message_id) if e.message_id else None,
                "payload": e.payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in self.request_event_manager.list_for_request(db, request.id)
        ]
        return detail

    # -- speaking into a thread --------------------------------------------

    def send_moderator_message(
        self,
        db: Session,
        request_id: int,
        *,
        group_id: UUID,
        author_member_id: UUID,
        body: str,
        recipient_ids: list[UUID] | None = None,
    ) -> dict:
        """Send a moderator's own words into an open request.

        Distinct from fan-out in every way that matters: a person wrote this, so
        the row records them in ``author_member_id`` and carries
        ``moderator_clarification``. That is what lets the thread show "the
        moderator asked" rather than attributing their question to the group.

        Defaults to the requester alone. A clarification is usually a question
        for the person who asked, and broadcasting it to everyone who received
        the original would be a surprising default for a moderator typing into
        a thread.
        """
        request = self._require_open(db, request_id, group_id)
        body = (body or "").strip()
        if not body:
            raise RequestError("Message body is required.")

        targets = recipient_ids or [request.requester_id]
        recipients = self._load_active_recipients(
            db,
            group_id=group_id,
            recipient_ids=list(dict.fromkeys(targets)),
        )
        if not recipients:
            raise NoRecipientsError("No active recipient for this message.")

        try:
            from_number = self.routing_service.resolve_from_number(db, request.group)
        except RoutingError as exc:
            raise RequestError(str(exc)) from exc

        # The recipient sees the group's number, so without this the question
        # reads as coming from the group itself. ``send_message`` adds the
        # "(Moderator)" part, from the kind.
        sender_name = self.membership_manager.get_display_names(
            db,
            group_id=group_id,
            member_ids=[author_member_id],
        ).get(author_member_id)

        sent: list[str] = []
        failures: list[dict] = []
        for recipient in recipients:
            try:
                message = self.messaging_service.send_message(
                    db,
                    group=request.group,
                    to_member=recipient,
                    from_phone_number=from_number,
                    body=body,
                    sender_name=sender_name,
                    kind=MessageKind.MODERATOR_CLARIFICATION,
                    author_member_id=author_member_id,
                    request_id=request.id,
                    parent_message_id=request.original_message_id,
                )
                sent.append(str(message.id))
            except SmsProviderError as exc:
                logger.exception(
                    "moderator_message_failed",
                    extra={"request_id": request.id},
                )
                failures.append({"member_id": str(recipient.id), "error": str(exc)})

        db.commit()
        return {"sent_message_ids": sent, "failures": failures}

    # -- closing ------------------------------------------------------------

    def complete(self, db: Session, request_id: int, *, group_id: UUID) -> dict:
        """The requester got what they needed."""
        return self._resolve(
            db,
            request_id,
            group_id=group_id,
            event_type=RequestEventType.COMPLETED,
            apply=self.request_manager.complete,
        )

    def cancel(self, db: Session, request_id: int, *, group_id: UUID) -> dict:
        """The request is withdrawn; it was never fulfilled."""
        return self._resolve(
            db,
            request_id,
            group_id=group_id,
            event_type=RequestEventType.CANCELLED,
            apply=self.request_manager.cancel,
        )

    def sweep_expired(self, db: Session, *, now: datetime | None = None) -> int:
        """Advance the lifecycle of requests nobody closed. Run on a schedule.

        Two bounds, one outcome. Inactivity is the normal one: a conversation
        that has gone quiet is over, and leaving it open makes the next
        unrelated SMS from those members a reply to it. Expiry is the ceiling
        for a request that keeps seeing activity yet never resolves.

        Both land on ``status = 'expired'`` with an ``EXPIRED`` event, because
        they mean the same thing to a moderator -- closed without resolution.
        Only the event payload's ``reason`` distinguishes them, which keeps the
        status vocabulary at four values.

        Nothing here is a classification fix. ``determine_inbound_kind`` is
        already correct; it was being handed an open request that should have
        been closed hours earlier.
        """
        now = now or datetime.now(timezone.utc)
        inactive_before = now - Config.REQUEST_INACTIVITY_AFTER
        stale = self.request_manager.list_open_needing_close(
            db,
            now=now,
            inactive_before=inactive_before,
        )
        reasons: dict[str, int] = {}
        for request in stale:
            reason = self._close_reason(request, now=now)
            reasons[reason] = reasons.get(reason, 0) + 1
            self.request_manager.expire(db, request)
            self.request_event_manager.record(
                db,
                request_id=request.id,
                event_type=RequestEventType.EXPIRED,
                # Both timestamps, not just the deciding one: reading the trail
                # later, "why did this close" is only answerable next to the
                # values it was judged against.
                payload={
                    "reason": reason,
                    "expires_at": self._iso(request.expires_at),
                    "last_activity_at": self._iso(request.last_activity_at),
                },
            )
        db.commit()
        if stale:
            logger.info(
                "requests_expired",
                extra={"count": len(stale), "reasons": reasons},
            )
        return len(stale)

    @staticmethod
    def _close_reason(request: Requests, *, now: datetime) -> str:
        """Which bound closed this request.

        The lifetime ceiling wins when both apply: it is the harder limit, and
        a request past 72 hours is finished whether or not it was also quiet.
        """
        if request.expires_at is not None and request.expires_at <= now:
            return "maximum_lifetime"
        return "inactivity"

    def _resolve(
        self,
        db: Session,
        request_id: int,
        *,
        group_id: UUID,
        event_type: RequestEventType,
        apply,
    ) -> dict:
        request = self._require_open(db, request_id, group_id)
        apply(db, request)
        self.request_event_manager.record(
            db,
            request_id=request.id,
            event_type=event_type,
        )
        db.commit()
        return self._summary(db, request)

    # -- lookups ------------------------------------------------------------

    def _require_request(
        self,
        db: Session,
        request_id: int,
        group_id: UUID,
    ) -> Requests:
        """Cross-group ids look like not-found, leaking no existence."""
        request = self.request_manager.find_for_group(
            db,
            group_id=group_id,
            request_id=request_id,
        )
        if request is None:
            raise RequestNotFoundError("Request not found.")
        return request

    def _require_open(self, db: Session, request_id: int, group_id: UUID) -> Requests:
        request = self._require_request(db, request_id, group_id)
        if request.status != "open":
            raise RequestNotOpenError(
                f"Request is not open (status={request.status})."
            )
        return request

    def _load_active_recipients(
        self,
        db: Session,
        *,
        group_id: UUID,
        recipient_ids: list[UUID],
    ) -> list[Member]:
        members: list[Member] = []
        for member_id in recipient_ids:
            membership = self.membership_manager.get_active_membership(
                db,
                member_id=member_id,
                group_id=group_id,
            )
            if membership is not None and membership.member is not None:
                members.append(membership.member)
        return members

    # -- serialization ------------------------------------------------------

    def _summary(
        self,
        db: Session,
        request: Requests,
        rollup: dict | None = None,
    ) -> dict:
        """The request, plus the activity rollup its caller already fetched.

        ``rollup`` is passed in rather than queried here so a list of a hundred
        requests costs one extra query instead of a hundred.
        """
        rollup = rollup or {}
        return {
            "id": request.id,
            "group_id": str(request.group_id),
            "status": request.status,
            "request_type": request.request_type,
            "summary": request.summary,
            "confidence": (
                float(request.confidence) if request.confidence is not None else None
            ),
            "extracted_filters": request.extracted_filters,
            # The vector itself is never serialized: it is a thousand floats of
            # no use to a browser.
            "has_embedding": request.embedding is not None,
            "model_name": request.model_name,
            "requester": self._member_brief(db, request.requester_id, request.group_id),
            "original_message_id": (
                str(request.original_message_id)
                if request.original_message_id
                else None
            ),
            "created_at": self._iso(request.created_at),
            "completed_at": self._iso(request.completed_at),
            "cancelled_at": self._iso(request.cancelled_at),
            "expires_at": self._iso(request.expires_at),
            # Members party to the request: the requester, whoever fan-out
            # reached, and anyone who answered. A moderator is not one of them.
            "participant_count": rollup.get("participant_count", 0),
            "message_count": rollup.get("message_count", 0),
            # From the column, not the rollup: this is the same value the sweep
            # judges inactivity against, so what a moderator sees and what
            # closes the request can never disagree.
            "last_activity_at": self._iso(request.last_activity_at),
            # Whether a message in this thread is waiting on a human. Not a
            # request status: a request can be open with or without this.
            "needs_review": rollup.get("needs_review", False),
        }

    def _message_brief(self, db: Session, message: Message) -> dict:
        return {
            "id": str(message.id),
            "direction": message.direction,
            "sender_role": message.sender_role,
            "kind": message.kind,
            "body": message.body,
            "workflow_status": message.workflow_status,
            # For a fan-out copy this names the authorized message it came
            # from, which is the identity of that routing operation: it is how
            # a reader groups copies without a window or an array position.
            "parent_message_id": (
                str(message.parent_message_id) if message.parent_message_id else None
            ),
            # Who it is about, and who wrote it -- different questions, so the
            # thread can render "moderator → Alice" correctly.
            "member": self._member_brief(db, message.member_id, message.group_id),
            "author": self._member_brief(
                db, message.author_member_id, message.group_id
            ),
            "created_at": self._iso(message.created_at),
        }

    def _member_brief(
        self,
        db: Session,
        member_id: UUID | None,
        group_id: UUID,
    ) -> dict | None:
        if member_id is None:
            return None
        member = db.query(Member).filter(Member.id == member_id).first()
        if member is None:
            return {"id": str(member_id)}
        membership = self.membership_manager.get_membership(
            db,
            member_id=member.id,
            group_id=group_id,
        )
        profile = membership.profile if membership is not None else None
        return {
            "id": str(member.id),
            "name": profile.display_name if profile is not None else member.name,
            "phone_number": member.phone_number,
        }

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None
