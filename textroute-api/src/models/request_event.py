from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.message import Message
    from src.models.requests import Requests


class RequestEvent(Base):
    """Machine-generated activity on a request.

    Deliberately not a message: keeping ``messages`` to human communication is
    what lets the moderator thread stay readable, and it gives the audit trail
    its own queryable shape rather than leaving it stringified in
    ``processing_notes``.
    """

    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("requests.id"),
        nullable=False,
        index=True,
    )
    # Set when the event concerns one specific message, which for delivery
    # outcomes is that recipient's fan-out copy.
    message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    request: Mapped["Requests"] = relationship(back_populates="events")
    message: Mapped["Message | None"] = relationship()

    __table_args__ = (
        # Closed vocabulary; a seventh event should be a deliberate migration.
        # Note the absence of 'partially_delivered': delivery is recorded per
        # recipient, so a partial fan-out is a mix of 'delivered' and
        # 'delivery_failed'. The aggregate lives on messages.workflow_status and
        # is never stored in two places.
        CheckConstraint(
            "event_type IN ('authorized', 'delivered', 'delivery_failed', "
            "'completed', 'cancelled', 'expired')",
            name="request_events_event_type_check",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'",
            name="request_events_payload_is_object",
        ),
    )
