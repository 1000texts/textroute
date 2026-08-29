"""Bulk member enrollment for an authenticated group.

Routes pass ``group_id`` from the session. Consent attestation is assumed at
the API boundary; this service records profile + consent rows.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.managers.membership_manager import MembershipManager
from src.core.phone_normalize import normalize_phone_number


class DuplicateMemberPhoneError(ValueError):
    """A phone number collides with another member's."""


class MemberNotFoundError(LookupError):
    """No such membership in this group."""


class LastModeratorError(ValueError):
    """The change would leave the group with no active moderator."""


# Mirrors the group_memberships role/status check constraints. Validating here
# turns a would-be 500 from the database into a 400 with a usable message.
VALID_ROLES = frozenset({"member", "moderator"})
VALID_STATUSES = frozenset(
    {"pending", "active", "declined", "removed", "opted_out"}
)


@dataclass(frozen=True)
class MemberEnrollment:
    phone_number: str
    name: str


@dataclass(frozen=True)
class AddedMember:
    member_id: UUID
    membership_id: UUID
    phone_number: str
    name: str


class MemberService:
    """Bulk member enrollment. Owns the all-or-nothing transaction."""

    def __init__(self, membership_manager: MembershipManager | None = None):
        self.membership_manager = membership_manager or MembershipManager()

    def add_members(
        self,
        db: Session,
        *,
        group_id: UUID,
        enrollments: list[MemberEnrollment],
    ) -> list[AddedMember]:
        """Normalize first, then write; any failure rolls back the whole batch."""
        normalized_enrollments = self._normalize(enrollments)
        added: list[AddedMember] = []

        try:
            for enrollment in normalized_enrollments:
                member = self.membership_manager.get_or_create_by_phone(
                    db,
                    enrollment.phone_number,
                    name=enrollment.name,
                )
                # join_group flushes; session already tracks the membership.
                membership = self.membership_manager.join_group(
                    db,
                    member_id=member.id,
                    group_id=group_id,
                    role="member",
                    status="active",
                )
                membership.consented_at = datetime.now(timezone.utc)

                self.membership_manager.upsert_profile(
                    db,
                    membership_id=membership.id,
                    display_name=enrollment.name,
                )
                for consent_type in ("group_membership", "receive_messages"):
                    self.membership_manager.grant_consent(
                        db,
                        membership_id=membership.id,
                        consent_type=consent_type,
                    )

                added.append(
                    AddedMember(
                        member_id=member.id,
                        membership_id=membership.id,
                        phone_number=member.phone_number,
                        name=enrollment.name,
                    )
                )

            db.commit()
        except Exception:
            db.rollback()
            raise

        return added

    def list_members(self, db: Session, *, group_id: UUID) -> list[dict]:
        """The moderator directory: every membership, active or not."""
        memberships = self.membership_manager.list_memberships(db, group_id)
        return [
            self._serialize(membership)
            for membership in memberships
            if membership.member is not None
        ]

    def update_member(
        self,
        db: Session,
        *,
        group_id: UUID,
        membership_id: UUID,
        name: str,
        phone_number: str,
        role: str,
        status: str,
    ) -> dict:
        """Apply a moderator's edits to one membership. Owns the transaction."""
        membership = self.membership_manager.get_membership_by_id(
            db,
            membership_id=membership_id,
            group_id=group_id,
        )
        if membership is None or membership.member is None:
            raise MemberNotFoundError("No such member in this group.")

        name = name.strip()
        if not name:
            raise ValueError("Member name is required.")
        if role not in VALID_ROLES:
            raise ValueError(f"Unknown role: {role}")
        if status not in VALID_STATUSES:
            raise ValueError(f"Unknown status: {status}")

        normalized_phone = normalize_phone_number(phone_number)

        # A group whose last moderator is demoted or deactivated can no longer
        # be administered by anyone, so refuse rather than strand it.
        losing_moderator = membership.role == "moderator" and (
            role != "moderator" or status != "active"
        )
        if losing_moderator and self._other_active_moderators(db, membership) == 0:
            raise LastModeratorError(
                "This is the group's only active moderator."
            )

        try:
            member = membership.member
            if normalized_phone != member.phone_number:
                # members rows are shared across groups, so the number has to
                # stay globally unique.
                existing = self.membership_manager.get_by_phone(
                    db,
                    normalized_phone,
                )
                if existing is not None and existing.id != member.id:
                    raise DuplicateMemberPhoneError(
                        "Another member already uses that phone number."
                    )
                member.phone_number = normalized_phone

            # The edited name is group-scoped, so it belongs on the profile the
            # directory reads first. members.name is only backfilled, never
            # overwritten: it is shared with every other group.
            if not member.name:
                member.name = name
            self.membership_manager.upsert_profile(
                db,
                membership_id=membership.id,
                display_name=name,
            )

            was_active = membership.status == "active"
            membership.role = role
            membership.status = status
            now = datetime.now(timezone.utc)
            if status == "active" and membership.joined_at is None:
                membership.joined_at = now
            if was_active and status != "active":
                membership.removed_at = now

            db.add(member)
            db.add(membership)
            db.commit()
        except Exception:
            db.rollback()
            raise

        db.refresh(membership)
        return self._serialize(membership)

    def _other_active_moderators(self, db: Session, membership) -> int:
        return sum(
            1
            for other in self.membership_manager.list_memberships(
                db,
                membership.group_id,
            )
            if other.id != membership.id
            and other.role == "moderator"
            and other.status == "active"
        )

    @staticmethod
    def _serialize(membership) -> dict:
        return {
            "member_id": str(membership.member.id),
            "membership_id": str(membership.id),
            "phone_number": membership.member.phone_number,
            "name": (
                membership.profile.display_name
                if membership.profile is not None
                else membership.member.name
            ),
            "role": membership.role,
            "status": membership.status,
            "joined_at": (
                membership.joined_at.isoformat()
                if membership.joined_at is not None
                else None
            ),
            # Membership timestamps rather than the member's: the same person
            # can belong to several groups, and the moderator is looking at
            # this group's record of them.
            "created_at": membership.created_at.isoformat(),
            "updated_at": membership.updated_at.isoformat(),
        }

    @staticmethod
    def _normalize(enrollments: list[MemberEnrollment]) -> list[MemberEnrollment]:
        normalized: list[MemberEnrollment] = []
        seen: set[str] = set()
        for enrollment in enrollments:
            phone_number = normalize_phone_number(enrollment.phone_number)
            name = enrollment.name.strip()
            if not name:
                raise ValueError("Member name is required.")
            if phone_number in seen:
                raise DuplicateMemberPhoneError(
                    f"Phone number appears more than once: {phone_number}"
                )
            seen.add(phone_number)
            normalized.append(
                MemberEnrollment(phone_number=phone_number, name=name)
            )
        return normalized
