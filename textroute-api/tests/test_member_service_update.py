"""Editing one membership from the moderator directory.

The interesting cases are the ones where a single edit touches two different
rows: the name is group-scoped and lives on the profile, while the phone number
lives on the shared members row and must stay globally unique.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.phone_normalize import InvalidPhoneNumberError
from src.services.member_service import (
    DuplicateMemberPhoneError,
    LastModeratorError,
    MemberNotFoundError,
    MemberService,
)

GROUP_ID = uuid4()
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _membership(*, role="member", status="active", joined=True, name="Ada"):
    return SimpleNamespace(
        id=uuid4(),
        group_id=GROUP_ID,
        member=SimpleNamespace(id=uuid4(), phone_number="+15551234567", name=name),
        profile=SimpleNamespace(display_name=name),
        role=role,
        status=status,
        joined_at=NOW if joined else None,
        removed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _service(membership, *, others=(), phone_owner=None):
    manager = MagicMock()
    manager.get_membership_by_id.return_value = membership
    manager.list_memberships.return_value = [membership, *others]
    manager.get_by_phone.return_value = phone_owner
    return MemberService(membership_manager=manager), manager


def _edit(membership, **overrides):
    payload = {
        "name": "Ada",
        "phone_number": membership.member.phone_number,
        "role": membership.role,
        "status": membership.status,
    }
    payload.update(overrides)
    return payload


def test_the_edited_name_goes_to_the_group_scoped_profile():
    membership = _membership()
    service, manager = _service(membership)
    db = MagicMock()

    service.update_member(
        db,
        group_id=GROUP_ID,
        membership_id=membership.id,
        **_edit(membership, name="Ada L."),
    )

    kwargs = manager.upsert_profile.call_args.kwargs
    assert kwargs["membership_id"] == membership.id
    assert kwargs["display_name"] == "Ada L."
    db.commit.assert_called_once()


def test_an_existing_shared_member_name_is_not_overwritten():
    """members.name is shared with every other group this person belongs to."""
    membership = _membership(name="Ada")
    service, _ = _service(membership)

    service.update_member(
        db=MagicMock(),
        group_id=GROUP_ID,
        membership_id=membership.id,
        **_edit(membership, name="Ada L."),
    )

    assert membership.member.name == "Ada"


def test_a_missing_shared_member_name_is_backfilled():
    membership = _membership(name=None)
    membership.member.name = None
    service, _ = _service(membership)

    service.update_member(
        db=MagicMock(),
        group_id=GROUP_ID,
        membership_id=membership.id,
        **_edit(membership, name="Ada"),
    )

    assert membership.member.name == "Ada"


def test_the_phone_number_is_normalized_before_it_is_stored():
    membership = _membership()
    service, _ = _service(membership)

    service.update_member(
        db=MagicMock(),
        group_id=GROUP_ID,
        membership_id=membership.id,
        **_edit(membership, phone_number="(555) 987-6543"),
    )

    assert membership.member.phone_number == "+15559876543"


def test_a_phone_number_owned_by_someone_else_is_rejected():
    membership = _membership()
    intruder = SimpleNamespace(id=uuid4())
    service, _ = _service(membership, phone_owner=intruder)
    db = MagicMock()

    with pytest.raises(DuplicateMemberPhoneError):
        service.update_member(
            db,
            group_id=GROUP_ID,
            membership_id=membership.id,
            **_edit(membership, phone_number="+15559876543"),
        )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_an_unparseable_phone_number_is_rejected_before_any_write():
    membership = _membership()
    service, manager = _service(membership)
    db = MagicMock()

    with pytest.raises(InvalidPhoneNumberError):
        service.update_member(
            db,
            group_id=GROUP_ID,
            membership_id=membership.id,
            **_edit(membership, phone_number="nonsense"),
        )

    manager.upsert_profile.assert_not_called()
    db.commit.assert_not_called()


def test_deactivating_stamps_removed_at():
    membership = _membership()
    service, _ = _service(
        membership,
        others=[_membership(role="moderator")],
    )

    service.update_member(
        db=MagicMock(),
        group_id=GROUP_ID,
        membership_id=membership.id,
        **_edit(membership, status="removed"),
    )

    assert membership.status == "removed"
    assert membership.removed_at is not None


def test_reactivating_a_member_who_never_joined_stamps_joined_at():
    membership = _membership(status="pending", joined=False)
    service, _ = _service(membership)

    service.update_member(
        db=MagicMock(),
        group_id=GROUP_ID,
        membership_id=membership.id,
        **_edit(membership, status="active"),
    )

    assert membership.joined_at is not None


def test_the_last_active_moderator_cannot_be_demoted():
    """A group with no moderator can no longer be administered by anyone."""
    membership = _membership(role="moderator")
    service, _ = _service(membership, others=[_membership(role="member")])
    db = MagicMock()

    with pytest.raises(LastModeratorError):
        service.update_member(
            db,
            group_id=GROUP_ID,
            membership_id=membership.id,
            **_edit(membership, role="member"),
        )

    db.commit.assert_not_called()


def test_the_last_active_moderator_cannot_be_deactivated():
    membership = _membership(role="moderator")
    service, _ = _service(membership)

    with pytest.raises(LastModeratorError):
        service.update_member(
            db=MagicMock(),
            group_id=GROUP_ID,
            membership_id=membership.id,
            **_edit(membership, status="removed"),
        )


def test_a_moderator_can_be_demoted_when_another_one_remains():
    membership = _membership(role="moderator")
    service, _ = _service(
        membership,
        others=[_membership(role="moderator")],
    )

    service.update_member(
        db=MagicMock(),
        group_id=GROUP_ID,
        membership_id=membership.id,
        **_edit(membership, role="member"),
    )

    assert membership.role == "member"


def test_a_membership_in_another_group_is_not_found():
    """group_id comes from the session, so this is the cross-group guard."""
    service, manager = _service(None)
    manager.get_membership_by_id.return_value = None

    with pytest.raises(MemberNotFoundError):
        service.update_member(
            db=MagicMock(),
            group_id=GROUP_ID,
            membership_id=uuid4(),
            name="Ada",
            phone_number="+15551234567",
            role="member",
            status="active",
        )


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_name_is_rejected(blank):
    membership = _membership()
    service, _ = _service(membership)
    db = MagicMock()

    with pytest.raises(ValueError):
        service.update_member(
            db,
            group_id=GROUP_ID,
            membership_id=membership.id,
            **_edit(membership, name=blank),
        )

    db.commit.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [("role", "admin"), ("status", "inactive")],
)
def test_values_the_database_would_reject_are_rejected_first(field, value):
    """'inactive' is not in the status check constraint; fail as 400, not 500."""
    membership = _membership()
    service, _ = _service(membership)

    with pytest.raises(ValueError):
        service.update_member(
            db=MagicMock(),
            group_id=GROUP_ID,
            membership_id=membership.id,
            **_edit(membership, **{field: value}),
        )
