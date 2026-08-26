"""Bulk member enrollment for an authenticated group.

Routes pass ``group_id`` from the session. Consent attestation is assumed at
the API boundary; this service records profile + consent rows.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.membership_manager import MembershipManager
from src.core.phone_normalize import normalize_phone_number


class DuplicateMemberPhoneError(ValueError):
    """A bulk request contains the same normalized phone more than once."""


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
        memberships = self.membership_manager.list_active_memberships(db, group_id)
        return [
            {
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
            }
            for membership in memberships
            if membership.member is not None
        ]

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
