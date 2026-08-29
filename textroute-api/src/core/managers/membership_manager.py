from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.phone_normalize import normalize_phone_number
from src.models import (
    GroupMembership,
    Member,
    MemberProfile,
    MembershipConsent,
)


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
        name: str | None = None,
    ) -> Member:
        """Find the member for this number, creating one if needed.

        ``name`` fills ``members.name`` on creation, and backfills it for a
        member who has none. It never replaces an existing name: the same
        person may be enrolled by someone else later, and a stale or careless
        entry should not silently rename them.
        """
        normalized = normalize_phone_number(phone_number)
        member = self.get_by_phone(db, normalized)

        if member is None:
            member = Member(phone_number=normalized, name=name)
            db.add(member)
            db.flush()
        elif name and not member.name:
            member.name = name
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

    def list_active_memberships(
        self,
        db: Session,
        group_id: UUID,
    ) -> list[GroupMembership]:
        return (
            db.query(GroupMembership)
            .filter(
                GroupMembership.group_id == group_id,
                GroupMembership.status == "active",
            )
            .all()
        )

    def list_memberships(
        self,
        db: Session,
        group_id: UUID,
    ) -> list[GroupMembership]:
        """Every membership in the group, whatever its status.

        The moderator directory needs the non-active rows too, otherwise a
        member who was removed becomes invisible and unreactivatable. Routing
        must keep using ``list_active_memberships``.
        """
        return (
            db.query(GroupMembership)
            .filter(GroupMembership.group_id == group_id)
            .all()
        )

    def get_membership_by_id(
        self,
        db: Session,
        *,
        membership_id: UUID,
        group_id: UUID,
    ) -> GroupMembership | None:
        """Load one membership, scoped to the group.

        ``group_id`` comes from the session, so passing it here is what stops a
        moderator from reaching a membership in someone else's group by id.
        """
        return (
            db.query(GroupMembership)
            .filter(
                GroupMembership.id == membership_id,
                GroupMembership.group_id == group_id,
            )
            .first()
        )

    def get_membership(
        self,
        db: Session,
        *,
        member_id: UUID,
        group_id: UUID,
    ) -> GroupMembership | None:
        return (
            db.query(GroupMembership)
            .filter(
                GroupMembership.member_id == member_id,
                GroupMembership.group_id == group_id,
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
            # A bulk member add must never demote an existing moderator.
            if existing.role != "moderator" or role == "moderator":
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

    def upsert_profile(
        self,
        db: Session,
        *,
        membership_id: UUID,
        display_name: str,
    ) -> MemberProfile:
        profile = (
            db.query(MemberProfile)
            .filter(MemberProfile.membership_id == membership_id)
            .first()
        )
        if profile is None:
            profile = MemberProfile(
                membership_id=membership_id,
                display_name=display_name,
            )
        else:
            profile.display_name = display_name
        db.add(profile)
        db.flush()
        return profile

    def grant_consent(
        self,
        db: Session,
        *,
        membership_id: UUID,
        consent_type: str,
    ) -> MembershipConsent:
        consent = (
            db.query(MembershipConsent)
            .filter(
                MembershipConsent.membership_id == membership_id,
                MembershipConsent.consent_type == consent_type,
            )
            .first()
        )
        now = datetime.now(timezone.utc)
        if consent is None:
            consent = MembershipConsent(
                membership_id=membership_id,
                consent_type=consent_type,
                status="granted",
                responded_at=now,
            )
        else:
            consent.status = "granted"
            consent.responded_at = now
        db.add(consent)
        db.flush()
        return consent
