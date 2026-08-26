from datetime import datetime
from uuid import UUID
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.group_membership import GroupMembership
    from src.models.message import Message
    from src.models.requests import Requests


class Member(Base):
    __tablename__ = "members"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    phone_number: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100))
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

    memberships: Mapped[list["GroupMembership"]] = relationship(
        back_populates="member",
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="member",
    )
    requests: Mapped[list["Requests"]] = relationship(
        back_populates="requester",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("phone_number", name="members_phone_number_unique"),
    )
