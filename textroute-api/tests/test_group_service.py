"""Group creation, focusing on the moderator's identity.

The moderator is a member like any other, so their name has to land in the same
places a member's does: ``members.name`` and the per-membership profile the
members list reads first.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.services.group_service import GroupService


def _service():
    membership_manager = MagicMock()
    group_manager = MagicMock()
    phone_number_manager = MagicMock()

    member = SimpleNamespace(id=uuid4(), phone_number="+15551234567", name="Ada")
    membership = SimpleNamespace(id=uuid4())
    membership_manager.get_or_create_by_phone.return_value = member
    membership_manager.join_group.return_value = membership
    group_manager.create_group.return_value = SimpleNamespace(
        id=uuid4(),
        name="Neighbors",
        description=None,
        status="active",
    )
    phone_number_manager.assign_available_number.return_value = SimpleNamespace(
        phone_number="+15550001001",
    )

    service = GroupService(
        group_manager=group_manager,
        membership_manager=membership_manager,
        phone_number_manager=phone_number_manager,
    )
    return service, membership_manager, membership


def test_moderator_name_is_stored_on_the_member_row():
    db = MagicMock()
    service, membership_manager, _ = _service()

    result = service.create_group(
        db,
        name="Neighbors",
        description=None,
        moderator_phone_number="+15551234567",
        moderator_name="Ada",
    )

    assert membership_manager.get_or_create_by_phone.call_args.kwargs["name"] == "Ada"
    assert result["moderator_name"] == "Ada"
    db.commit.assert_called_once()


def test_moderator_name_is_also_stored_on_the_membership_profile():
    """The members list prefers the profile, so both have to be written."""
    db = MagicMock()
    service, membership_manager, membership = _service()

    service.create_group(
        db,
        name="Neighbors",
        description=None,
        moderator_phone_number="+15551234567",
        moderator_name="Ada",
    )

    membership_manager.upsert_profile.assert_called_once()
    kwargs = membership_manager.upsert_profile.call_args.kwargs
    assert kwargs["membership_id"] == membership.id
    assert kwargs["display_name"] == "Ada"


def test_surrounding_whitespace_is_stripped():
    db = MagicMock()
    service, membership_manager, _ = _service()

    service.create_group(
        db,
        name="Neighbors",
        description=None,
        moderator_phone_number="+15551234567",
        moderator_name="  Ada  ",
    )

    assert membership_manager.get_or_create_by_phone.call_args.kwargs["name"] == "Ada"


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_moderator_name_is_rejected_before_anything_is_written(blank):
    db = MagicMock()
    service, membership_manager, _ = _service()

    with pytest.raises(ValueError):
        service.create_group(
            db,
            name="Neighbors",
            description=None,
            moderator_phone_number="+15551234567",
            moderator_name=blank,
        )

    membership_manager.get_or_create_by_phone.assert_not_called()
    db.commit.assert_not_called()
