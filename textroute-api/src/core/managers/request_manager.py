"""Persistence for the request lifecycle.

A request is the parent workflow object; its messages are events within that
lifecycle. This manager flushes and never commits -- services own transactions.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, case, distinct, func, or_
from sqlalchemy.orm import Session

from src.domain.message_role import PARTICIPANT_KINDS, MessageKind
from src.domain.message_status import MessageWorkflowStatus
from src.models import Message, Requests


class RequestManager:

    def find_by_id(self, db: Session, request_id: int) -> Requests | None:
        return db.query(Requests).filter(Requests.id == request_id).first()

    def find_for_group(
        self,
        db: Session,
        *,
        group_id: UUID,
        request_id: int,
    ) -> Requests | None:
        """Group-scoped load: the guard against reaching another group's request."""
        return (
            db.query(Requests)
            .filter(Requests.id == request_id, Requests.group_id == group_id)
            .first()
        )

    def find_open_for_requester(
        self,
        db: Session,
        *,
        group_id: UUID,
        requester_id: UUID,
    ) -> Requests | None:
        """The requester's own live request, if they have one.

        A unique partial index guarantees at most one.
        """
        return (
            db.query(Requests)
            .filter(
                Requests.group_id == group_id,
                Requests.requester_id == requester_id,
                Requests.status == "open",
            )
            .first()
        )

    def find_open_for_participant(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
    ) -> Requests | None:
        """The most recent live request that reached this member.

        A fan-out copy records its recipient in ``member_id``, so participation
        is a lookup over explicit columns: no time window, no
        ``parent_message_id`` traversal, no inferred relationship. This is what
        lets a responder's "I have one" join the request it answers.
        """
        return (
            db.query(Requests)
            .join(Message, Message.request_id == Requests.id)
            .filter(
                Requests.group_id == group_id,
                Requests.status == "open",
                Message.kind == MessageKind.FANOUT_COPY.value,
                Message.member_id == member_id,
            )
            .order_by(Message.created_at.desc())
            .first()
        )

    def create(
        self,
        db: Session,
        *,
        group_id: UUID,
        requester_id: UUID,
        expires_at: datetime | None = None,
    ) -> Requests:
        request = Requests(
            group_id=group_id,
            requester_id=requester_id,
            status="open",
            expires_at=expires_at,
            # Explicit rather than left to the column default: a request is
            # created microseconds before its original message, and an idle
            # request must never look older than it is.
            last_activity_at=datetime.now(timezone.utc),
        )
        db.add(request)
        db.flush()
        return request

    def set_original_message(
        self,
        db: Session,
        request: Requests,
        message_id: UUID,
    ) -> Requests:
        """Close the loop after the first message exists.

        The FK is deferred precisely because these two rows point at each other.
        """
        request.original_message_id = message_id
        db.add(request)
        db.flush()
        return request

    def apply_analysis(
        self,
        db: Session,
        request: Requests,
        *,
        request_type: str | None,
        extracted_filters: dict,
        summary: str | None,
        embedding: list[float] | None,
        model_name: str | None,
        confidence: float | None = None,
    ) -> Requests:
        """Store what the analyzer understood about the request.

        Everything the analyzer produces lands here, on the request it
        describes. A caller that learns something new about a request should
        extend this rather than annotating one of its messages.
        """
        request.request_type = request_type
        request.extracted_filters = extracted_filters
        request.summary = summary
        request.embedding = embedding
        request.model_name = model_name
        request.confidence = confidence
        db.add(request)
        db.flush()
        return request

    def complete(self, db: Session, request: Requests) -> Requests:
        return self._close(db, request, status="completed", field="completed_at")

    def cancel(self, db: Session, request: Requests) -> Requests:
        return self._close(db, request, status="cancelled", field="cancelled_at")

    def expire(self, db: Session, request: Requests) -> Requests:
        # No expired_at column: the lifecycle records when it ended through
        # status plus the expired event, and expires_at already says when it
        # was due to.
        request.status = "expired"
        db.add(request)
        db.flush()
        return request

    def list_for_group(
        self,
        db: Session,
        *,
        group_id: UUID,
        statuses: list[str] | None = None,
        limit: int = 100,
    ) -> list[Requests]:
        query = db.query(Requests).filter(Requests.group_id == group_id)
        if statuses is not None:
            query = query.filter(Requests.status.in_(statuses))
        return query.order_by(Requests.created_at.desc()).limit(limit).all()

    def list_open_needing_close(
        self,
        db: Session,
        *,
        now: datetime,
        inactive_before: datetime,
    ) -> list[Requests]:
        """Open requests that either went quiet or ran out of time.

        One query for both bounds, because they are two reasons for the same
        outcome and a second query would be a second chance to disagree about
        which requests are still open.

        ``expires_at`` is nullable and an unset one means no ceiling, so it is
        guarded; ``last_activity_at`` is NOT NULL and needs no guard.
        """
        return (
            db.query(Requests)
            .filter(
                Requests.status == "open",
                or_(
                    and_(
                        Requests.expires_at.isnot(None),
                        Requests.expires_at <= now,
                    ),
                    Requests.last_activity_at <= inactive_before,
                ),
            )
            .all()
        )

    def summarize_activity(
        self,
        db: Session,
        *,
        request_ids: list[int],
    ) -> dict[int, dict]:
        """Per-request rollups in one pass, so a 100-row list is one query.

        Participants are member-side only: the moderator acts on a request
        without being a party to it. ``PARTICIPANT_KINDS`` holds that rule, and
        ``COUNT(DISTINCT ...)`` drops the NULLs the CASE produces for every
        other kind.

        Last activity is deliberately absent: it lives on
        ``requests.last_activity_at`` now, because the sweep needs to filter on
        it. Computing ``max(created_at)`` here as well would be a second answer
        to the same question, free to drift from the one that closes requests.
        """
        if not request_ids:
            return {}

        participant_kinds = [k.value for k in PARTICIPANT_KINDS]
        rows = (
            db.query(
                Message.request_id,
                func.count(Message.id),
                func.count(
                    distinct(
                        case(
                            (
                                Message.kind.in_(participant_kinds),
                                Message.member_id,
                            ),
                        )
                    )
                ),
                func.bool_or(
                    Message.workflow_status
                    == MessageWorkflowStatus.AWAITING_MODERATOR.value
                ),
            )
            .filter(Message.request_id.in_(request_ids))
            .group_by(Message.request_id)
            .all()
        )

        return {
            request_id: {
                "message_count": message_count,
                "participant_count": participant_count,
                "needs_review": bool(needs_review),
            }
            for (
                request_id,
                message_count,
                participant_count,
                needs_review,
            ) in rows
        }

    def load_thread(self, db: Session, request_id: int) -> list[Message]:
        """Every message in the request, oldest first.

        Includes outbound rows: in a thread the fan-out copies and moderator
        clarifications are part of the conversation, unlike the flat moderator
        feed where they are only delivery records.
        """
        return (
            db.query(Message)
            .filter(Message.request_id == request_id)
            .order_by(Message.created_at.asc())
            .all()
        )

    @staticmethod
    def _close(db: Session, request: Requests, *, status: str, field: str) -> Requests:
        request.status = status
        setattr(request, field, datetime.now(timezone.utc))
        db.add(request)
        db.flush()
        return request
