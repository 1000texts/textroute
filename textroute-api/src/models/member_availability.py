from datetime import time
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Time, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class MemberAvailability(Base):
    __tablename__ = "member_availability"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    membership_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("group_memberships.id"),
        nullable=False,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    timezone: Mapped[str | None] = mapped_column(String(50))

    membership: Mapped["GroupMembership"] = relationship(back_populates="availability")

    __table_args__ = (
        CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="member_availability_day_check",
        ),
    )
