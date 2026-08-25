from datetime import datetime
from uuid import UUID
from typing import TYPE_CHECKING
from sqlalchemy import CheckConstraint, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.group_membership import GroupMembership
    from src.models.phone_number import PhoneNumber


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'active'"),
    )
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
        back_populates="group",
    )
    phone_numbers: Mapped[list["PhoneNumber"]] = relationship(
        back_populates="group",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive')",
            name="groups_status_check",
        ),
    )
