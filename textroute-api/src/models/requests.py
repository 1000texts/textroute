from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Requests(Base):
    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )
    requester_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    request_text: Mapped[str] = mapped_column(Text, nullable=False)
    request_type: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_filters: Mapped[dict] = mapped_column(JSONB, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
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

    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(extracted_filters) = 'object'",
            name="extracted_filters_is_object",
        ),
    )

    requester = relationship(
        "Member",
        back_populates="requests",
        passive_deletes=True,
    )
