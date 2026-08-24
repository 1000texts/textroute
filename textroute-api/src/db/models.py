from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    Text,
    DateTime,
    CheckConstraint,
    String,
    func,
    UniqueConstraint,
    ForeignKey,
    text
)
from sqlalchemy.dialects.postgresql import JSONB
from pgvector.sqlalchemy import Vector
import uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import Boolean
from sqlalchemy.dialects.postgresql import UUID


class Base(DeclarativeBase):
    pass


class InboundMessage(Base):
    __tablename__ = "inbound_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    receiver = Column(String, nullable=False)
    message = Column(String, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now())


class Requests(Base):
    __tablename__ = "requests"

    # ----------------------------
    # Primary key
    # ----------------------------
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    # ----------------------------
    # Foreign key (member)
    # ----------------------------
    requester_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("members.member_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ----------------------------
    # Request content
    # ----------------------------
    request_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Raw user request text",
    )

    request_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Intent / schema name used to process this request",
    )

    extracted_filters: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        doc="Structured data extracted from the request",
    )

    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional summarized version of request_text",
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536),
        nullable=True,
        doc="Vector embedding of request_text or summary",
    )

    # ----------------------------
    # Metadata
    # ----------------------------
    schema_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("1"),
    )

    model_name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Model used to process the request",
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ----------------------------
    # Constraints
    # ----------------------------
    __table_args__ = (
        CheckConstraint(
            "jsonb_typeof(extracted_filters) = 'object'",
            name="extracted_filters_is_object",
        ),
    )

    # ----------------------------
    # ORM relationships (optional but recommended)
    # ----------------------------
    requester = relationship(
        "Member",
        back_populates="requests",
        passive_deletes=True,
    )


class Member(Base):
    __tablename__ = "members"

    member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )

    name: Mapped[str | None] = mapped_column(String)
    sender: Mapped[str] = mapped_column(String(50))
    receiver: Mapped[str] = mapped_column(String(50))
    is_need_info: Mapped[bool] = mapped_column(Boolean, default=True)
    is_need_consent: Mapped[bool] = mapped_column(Boolean, default=True)
    is_need_approval: Mapped[bool] = mapped_column(Boolean, default=True)

    requests: Mapped[list["Requests"]] = relationship(
        "Requests",
        back_populates="requester",
        cascade="all, delete-orphan",
    )

    __table_args__ = (UniqueConstraint("sender", "receiver", name="members_unique_1"),)
