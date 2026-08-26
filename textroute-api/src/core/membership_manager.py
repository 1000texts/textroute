from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.phone_normalize import normalize_phone_number
from src.models import GroupMembership, Member


class MembershipManager:

    def get_by_phone(
        self,
        db: Session,
        phone_number: str,
    ) -> Member | None:
        normalized = normalize_phone_number(phone_number)
        return db.query(Member).filter(Member.phone_number == normalized).first()

    def get_or_create_by_phone(
        self,
        db: Session,
        phone_number: str,
    ) -> Member:
        normalized = normalize_phone_number(phone_number)
        member = self.get_by_phone(db, normalized)

        if member is None:
            member = Member(phone_number=normalized)
            db.add(member)
            db.flush()

        return member

    def get_active_membership(
        self,
        db: Session,
        member_id: UUID,
        group_id: UUID,
    ) -> GroupMembership | None:
        return (
            db.query(GroupMembership)
            .filter(
                GroupMembership.member_id == member_id,
                GroupMembership.group_id == group_id,
                GroupMembership.status == "active",
            )
            .first()
        )

    def join_group(
        self,
        db: Session,
        member_id: UUID,
        group_id: UUID,
        role: str = "member",
        status: str = "active",
    ) -> GroupMembership:
        existing = (
            db.query(GroupMembership)
            .filter(
                GroupMembership.member_id == member_id,
                GroupMembership.group_id == group_id,
            )
            .first()
        )
        if existing is not None:
            existing.role = role
            existing.status = status
            if status == "active" and existing.joined_at is None:
                existing.joined_at = datetime.now(timezone.utc)
            db.add(existing)
            db.flush()
            return existing

        group_membership = GroupMembership(
            member_id=member_id,
            group_id=group_id,
            role=role,
            status=status,
            joined_at=datetime.now(timezone.utc),
        )

        db.add(group_membership)
        db.flush()

        return group_membership
