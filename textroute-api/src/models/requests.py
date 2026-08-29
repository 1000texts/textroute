from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
    text,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.group import Group
    from src.models.member import Member
    from src.models.message import Message


class Requests(Base):
    """Workflow object derived from one or more related messages."""

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id", name="requests_group_id_fkey"),
        nullable=False,
        index=True,
    )
    requester_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("members.id", name="requests_requester_id_fkey"),
        nullable=False,
        index=True,
    )
    # Deferred because messages.request_id points back to this table.
    original_message_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "messages.id",
            name="requests_original_message_id_fkey",
            use_alter=True,
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'open'"),
    )
    request_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_filters: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How sure the analyzer was about request_type. Nullable rather than
    # defaulted: no analysis and a genuinely unsure answer are different facts.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 1024 matches the configured Qwen3 embedding model. Changing model means
    # changing this and reindexing; ivfflat needs a fixed dimension.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1024),
        nullable=True,
    )
    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    group = relationship("Group")
    requester = relationship(
        "Member",
        back_populates="requests",
    )
    messages = relationship(
        "Message",
        foreign_keys="Message.request_id",
        back_populates="request",
    )
    original_message = relationship(
        "Message",
        foreign_keys=[original_message_id],
        post_update=True,
    )
    events = relationship(
        "RequestEvent",
        back_populates="request",
        order_by="RequestEvent.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'completed', 'cancelled', 'expired')",
            name="requests_status_check",
        ),
        CheckConstraint(
            "jsonb_typeof(extracted_filters) = 'object'",
            name="requests_extracted_filters_is_object",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="requests_confidence_range",
        ),
    )
