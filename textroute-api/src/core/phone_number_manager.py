from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.core.phone_normalize import normalize_phone_number
from src.models import PhoneNumber


class PhoneNumberManager:

    def find_by_number(
        self,
        db: Session,
        phone_number: str,
    ) -> PhoneNumber | None:
        normalized = normalize_phone_number(phone_number)
        return (
            db.query(PhoneNumber).filter(PhoneNumber.phone_number == normalized).first()
        )

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
