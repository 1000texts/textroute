from datetime import datetime, timezone
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
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from src.models import PhoneNumber
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


class PhoneNumberManager:

    def assign_available_number(
        self,
        db: Session,
        group_id: UUID,
    ) -> PhoneNumber:

        phone_number = (
            db.query(PhoneNumber)
            .filter(PhoneNumber.status == "available")
            .order_by(func.random())
            .with_for_update()
            .first()
        )

        if phone_number is None:
            raise ValueError("No available TextRoute phone numbers.")

        phone_number.group_id = group_id
        phone_number.status = "assigned"
        phone_number.assigned_at = datetime.now(timezone.utc)

        db.add(phone_number)
        db.flush()

        return phone_number
