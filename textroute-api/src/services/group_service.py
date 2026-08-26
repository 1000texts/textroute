"""Group lifecycle orchestration.

Managers flush only; this service owns ``commit`` / ``rollback``.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from src.core.group_manager import GroupManager
from src.core.membership_manager import MembershipManager
from src.core.phone_number_manager import PhoneNumberManager
from src.models import Group


class GroupService:
    def __init__(
        self,
        group_manager: GroupManager | None = None,
        membership_manager: MembershipManager | None = None,
        phone_number_manager: PhoneNumberManager | None = None,
    ):
        self.group_manager = group_manager or GroupManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()

    def create_group(
        self,
        db: Session,
        *,
        name: str,
        description: str | None,
        moderator_phone_number: str,
    ) -> dict:
        moderator = self.membership_manager.get_or_create_by_phone(
            db,
            moderator_phone_number,
        )

        group = self.group_manager.create_group(
            db,
            name=name,
            description=description,
        )

        self.membership_manager.join_group(
            db,
            member_id=moderator.id,
            group_id=group.id,
            role="moderator",
            status="active",
        )

        phone_number = self.phone_number_manager.assign_available_number(
            db,
            group_id=group.id,
        )

        db.commit()

        return {
            "id": str(group.id),
            "name": group.name,
            "description": group.description,
            "status": group.status,
            "moderator_member_id": str(moderator.id),
            "phone_number": phone_number.phone_number,
        }

    def add_member(
        self,
        db: Session,
        *,
        group_id: UUID,
        phone_number: str,
        name: str | None = None,
        role: str = "member",
    ) -> dict:
        group = db.query(Group).filter(Group.id == group_id).first()
        if group is None:
            raise LookupError("Group not found.")

        member = self.membership_manager.get_or_create_by_phone(db, phone_number)
        if name and not member.name:
            member.name = name
            db.add(member)
            db.flush()

        membership = self.membership_manager.join_group(
            db,
            member_id=member.id,
            group_id=group.id,
            role=role,
            status="active",
        )
        db.commit()

        return {
            "id": str(member.id),
            "group_id": str(group.id),
            "phone_number": member.phone_number,
            "name": member.name,
            "role": membership.role,
            "status": membership.status,
        }

    def list_members(self, db: Session, group_id: UUID) -> list[dict]:
        group = db.query(Group).filter(Group.id == group_id).first()
        if group is None:
            raise LookupError("Group not found.")

        memberships = self.membership_manager.list_active_memberships(db, group_id)
        return [
            {
                "id": str(m.member.id),
                "phone_number": m.member.phone_number,
                "name": m.member.name,
                "role": m.role,
                "status": m.status,
            }
            for m in memberships
            if m.member is not None
        ]
