"""Persistence for the request audit trail.

Events are machine-generated activity -- routing authorizations, per-recipient
delivery outcomes, lifecycle transitions -- kept out of ``messages`` so that
table stays human communication and the moderator thread stays readable.

Flushes and never commits: the caller that made the thing happen also owns the
transaction, so an event cannot survive a rolled-back action.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from src.domain.message_role import RequestEventType
from src.models import RequestEvent


class RequestEventManager:

    def record(
        self,
        db: Session,
        *,
        request_id: int,
        event_type: RequestEventType,
        message_id: UUID | None = None,
        payload: dict | None = None,
    ) -> RequestEvent:
        event = RequestEvent(
            request_id=request_id,
            message_id=message_id,
            event_type=event_type.value,
            payload=payload or {},
        )
        db.add(event)
        db.flush()
        return event

    def list_for_request(self, db: Session, request_id: int) -> list[RequestEvent]:
        return (
            db.query(RequestEvent)
            .filter(RequestEvent.request_id == request_id)
            .order_by(RequestEvent.created_at.asc())
            .all()
        )
