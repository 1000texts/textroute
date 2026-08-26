from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.domain.message_status import MessageWorkflowStatus
from src.models.base import Base

if TYPE_CHECKING:
    from src.models.group import Group
    from src.models.member import Member


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("members.id"),
        nullable=True,
        index=True,
    )
    parent_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("messages.id"),
        nullable=True,
        index=True,
    )
    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    from_phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    to_phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    workflow_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        server_default=text(f"'{MessageWorkflowStatus.RECEIVED.value}'"),
    )
    intent: Mapped[str | None] = mapped_column(String(64))
    constraints: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    suggested_recipient_ids: Mapped[list[UUID] | None] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True))
    )
    approved_recipient_ids: Mapped[list[UUID] | None] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True))
    )
    processing_notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    group: Mapped["Group"] = relationship(back_populates="messages")
    member: Mapped["Member | None"] = relationship(back_populates="messages")
    parent: Mapped["Message | None"] = relationship(
        remote_side=[id],
        foreign_keys=[parent_message_id],
    )

    __table_args__ = (
        CheckConstraint(
            "direction IN ('inbound', 'outbound')",
            name="messages_direction_check",
        ),
        CheckConstraint(
            "workflow_status IN ("
            "'received', 'processing', 'awaiting_moderator', 'approved', "
            "'delivering', 'sent', 'delivered', 'partially_delivered', "
            "'processing_failed', 'moderator_rejected', 'delivery_failed')",
            name="messages_workflow_status_check",
        ),
    )
