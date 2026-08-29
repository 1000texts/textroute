"""Group creation: moderator membership + assign an available TextRoute number.

Managers flush only; this service owns ``commit`` / ``rollback``.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from src.core.managers.group_manager import GroupManager
from src.core.managers.membership_manager import MembershipManager
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.domain.routing_policy import IMPLEMENTED_POLICIES
from src.models import Group


class UnsupportedRoutingPolicyError(Exception):
    """A recognized-but-unimplemented or unknown routing policy was requested."""


class GroupService:
    """Bootstrap a group for the vertical slice (one assigned line per group)."""

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
        moderator_name: str,
    ) -> dict:
        """Atomic create: group + moderator membership + phone assignment."""
        moderator_name = moderator_name.strip()
        if not moderator_name:
            raise ValueError("Moderator name is required.")

        moderator = self.membership_manager.get_or_create_by_phone(
            db,
            moderator_phone_number,
            name=moderator_name,
        )

        group = self.group_manager.create_group(
            db,
            name=name,
            description=description,
        )

        membership = self.membership_manager.join_group(
            db,
            member_id=moderator.id,
            group_id=group.id,
            role="moderator",
            status="active",
        )

        # The members list reads the per-membership profile first and falls back
        # to members.name, so write both. Otherwise the moderator's own name
        # would render through a different path than everyone they enroll.
        self.membership_manager.upsert_profile(
            db,
            membership_id=membership.id,
            display_name=moderator_name,
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
            "moderator_name": moderator.name,
            "phone_number": phone_number.phone_number,
        }

    def get_settings(self, db: Session, group_id: UUID) -> dict:
        group = self.group_manager.get_group(db, group_id)
        if group is None:
            raise LookupError("Group not found.")
        return self._settings(group)

    def set_routing_policy(
        self,
        db: Session,
        group_id: UUID,
        *,
        routing_policy: str,
    ) -> dict:
        """Change how new requests from this group are routed.

        Rejects policies the router cannot honor yet, rather than silently
        accepting a value that would fall back to moderation at runtime.
        """
        if routing_policy not in {p.value for p in IMPLEMENTED_POLICIES}:
            raise UnsupportedRoutingPolicyError(
                f"Routing policy {routing_policy!r} is not implemented."
            )

        group = self.group_manager.get_group(db, group_id)
        if group is None:
            raise LookupError("Group not found.")

        group.routing_policy = routing_policy
        db.add(group)
        db.commit()
        return self._settings(group)

    def _settings(self, group: Group) -> dict:
        return {
            "id": str(group.id),
            "name": group.name,
            "description": group.description,
            "status": group.status,
            "routing_policy": group.routing_policy,
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
                "name": (
                    m.profile.display_name
                    if m.profile is not None
                    else m.member.name
                ),
                "role": m.role,
                "status": m.status,
            }
            for m in memberships
            if m.member is not None
        ]
