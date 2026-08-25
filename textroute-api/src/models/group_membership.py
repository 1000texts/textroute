from datetime import datetime
from uuid import UUID
from typing import TYPE_CHECKING
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base

if TYPE_CHECKING:
    from src.models.group import Group
    from src.models.member import Member
    from src.models.member_profile import MemberProfile
    from src.models.member_item import MemberItem
    from src.models.member_skill import MemberSkill
    from src.models.member_interest import MemberInterest
    from src.models.member_availability import MemberAvailability
    from src.models.membership_consent import MembershipConsent


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    group_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("groups.id"),
        nullable=False,
    )
    member_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("members.id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'member'"),
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'pending'"),
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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

    group: Mapped["Group"] = relationship(back_populates="memberships")
    member: Mapped["Member"] = relationship(back_populates="memberships")
    profile: Mapped["MemberProfile | None"] = relationship(
        back_populates="membership",
        uselist=False,
    )
    items: Mapped[list["MemberItem"]] = relationship(back_populates="membership")
    skills: Mapped[list["MemberSkill"]] = relationship(back_populates="membership")
    interests: Mapped[list["MemberInterest"]] = relationship(
        back_populates="membership"
    )
    availability: Mapped[list["MemberAvailability"]] = relationship(
        back_populates="membership",
    )
    consents: Mapped[list["MembershipConsent"]] = relationship(
        back_populates="membership",
    )

    __table_args__ = (
        UniqueConstraint("group_id", "member_id", name="group_memberships_unique"),
        CheckConstraint(
            "role IN ('member', 'moderator')",
            name="group_memberships_role_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'declined', 'removed', 'opted_out')",
            name="group_memberships_status_check",
        ),
    )
