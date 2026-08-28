from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest

from src.core.managers.membership_manager import MembershipManager
from src.services.member_service import (
    DuplicateMemberPhoneError,
    MemberEnrollment,
    MemberService,
)


def test_add_members_is_all_or_nothing_service_transaction():
    db = MagicMock()
    manager = MagicMock()
    group_id = uuid4()
    first_member = SimpleNamespace(id=uuid4(), phone_number="+15551234567")
    second_member = SimpleNamespace(id=uuid4(), phone_number="+15557654321")
    first_membership = SimpleNamespace(id=uuid4(), consented_at=None)
    second_membership = SimpleNamespace(id=uuid4(), consented_at=None)
    manager.get_or_create_by_phone.side_effect = [first_member, second_member]
    manager.join_group.side_effect = [first_membership, second_membership]
    service = MemberService(manager)

    result = service.add_members(
        db,
        group_id=group_id,
        enrollments=[
            MemberEnrollment("(555) 123-4567", " Alice "),
            MemberEnrollment("+1 555 765 4321", "Bob"),
        ],
    )

    assert [member.phone_number for member in result] == [
        "+15551234567",
        "+15557654321",
    ]
    assert [member.name for member in result] == ["Alice", "Bob"]
    assert first_membership.consented_at is not None
    assert second_membership.consented_at is not None
    assert manager.upsert_profile.call_args_list == [
        call(
            db,
            membership_id=first_membership.id,
            display_name="Alice",
        ),
        call(
            db,
            membership_id=second_membership.id,
            display_name="Bob",
        ),
    ]
    assert manager.grant_consent.call_count == 4
    assert {
        consent_call.kwargs["consent_type"]
        for consent_call in manager.grant_consent.call_args_list
    } == {"group_membership", "receive_messages"}
    db.commit.assert_called_once()
    db.add.assert_not_called()


def test_add_members_rolls_back_on_failure():
    db = MagicMock()
    manager = MagicMock()
    group_id = uuid4()
    member = SimpleNamespace(id=uuid4(), phone_number="+15551234567")
    membership = SimpleNamespace(id=uuid4(), consented_at=None)
    manager.get_or_create_by_phone.return_value = member
    manager.join_group.return_value = membership
    manager.upsert_profile.side_effect = RuntimeError("profile write failed")
    service = MemberService(manager)

    with pytest.raises(RuntimeError, match="profile write failed"):
        service.add_members(
            db,
            group_id=group_id,
            enrollments=[MemberEnrollment("+15551234567", "Alice")],
        )

    db.commit.assert_not_called()
    db.rollback.assert_called_once()


def test_duplicate_normalized_phone_rejects_entire_batch():
    db = MagicMock()
    manager = MagicMock()
    service = MemberService(manager)

    with pytest.raises(DuplicateMemberPhoneError):
        service.add_members(
            db,
            group_id=uuid4(),
            enrollments=[
                MemberEnrollment("(555) 123-4567", "Alice"),
                MemberEnrollment("+15551234567", "Alice again"),
            ],
        )

    manager.get_or_create_by_phone.assert_not_called()
    db.commit.assert_not_called()


def test_blank_member_name_is_rejected_before_writes():
    db = MagicMock()
    manager = MagicMock()
    service = MemberService(manager)

    with pytest.raises(ValueError, match="name"):
        service.add_members(
            db,
            group_id=uuid4(),
            enrollments=[MemberEnrollment("+15551234567", "   ")],
        )

    manager.get_or_create_by_phone.assert_not_called()
    db.commit.assert_not_called()


def test_join_group_does_not_demote_existing_moderator():
    db = MagicMock()
    membership = SimpleNamespace(
        role="moderator",
        status="active",
        joined_at=object(),
    )
    db.query.return_value.filter.return_value.first.return_value = membership

    result = MembershipManager().join_group(
        db,
        member_id=uuid4(),
        group_id=uuid4(),
        role="member",
        status="active",
    )

    assert result.role == "moderator"


def test_profile_and_consent_upserts_are_idempotent():
    db = MagicMock()
    manager = MembershipManager()
    profile = SimpleNamespace(display_name="Old name")
    consent = SimpleNamespace(status="pending", responded_at=None)
    db.query.return_value.filter.return_value.first.side_effect = [
        profile,
        consent,
    ]
    membership_id = uuid4()

    updated_profile = manager.upsert_profile(
        db,
        membership_id=membership_id,
        display_name="New name",
    )
    updated_consent = manager.grant_consent(
        db,
        membership_id=membership_id,
        consent_type="group_membership",
    )

    assert updated_profile is profile
    assert profile.display_name == "New name"
    assert updated_consent is consent
    assert consent.status == "granted"
    assert consent.responded_at is not None
