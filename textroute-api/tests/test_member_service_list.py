"""Shape of the member directory the moderator UI renders.

The Members page shows each membership's timestamps, so they have to be in the
payload; and it shows the profile display name in preference to the member's own
name, because a group may know someone by a different name than they registered.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.services.member_service import MemberService

CREATED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
UPDATED = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
JOINED = datetime(2026, 1, 2, 3, 10, 0, tzinfo=timezone.utc)


def _membership(*, profile=None, name="Ada"):
    return SimpleNamespace(
        id=uuid4(),
        member=SimpleNamespace(id=uuid4(), phone_number="+15551234567", name=name),
        profile=profile,
        role="member",
        status="active",
        joined_at=JOINED,
        created_at=CREATED,
        updated_at=UPDATED,
    )


def _service(memberships):
    manager = MagicMock()
    # The directory deliberately lists non-active memberships too.
    manager.list_memberships.return_value = memberships
    return MemberService(membership_manager=manager)


def test_membership_timestamps_are_included():
    membership = _membership()
    service = _service([membership])

    [row] = service.list_members(MagicMock(), group_id=uuid4())

    assert row["created_at"] == CREATED.isoformat()
    assert row["updated_at"] == UPDATED.isoformat()
    assert row["joined_at"] == JOINED.isoformat()


def test_profile_display_name_wins_over_the_member_name():
    membership = _membership(
        profile=SimpleNamespace(display_name="Ada L."),
        name="Ada",
    )
    service = _service([membership])

    [row] = service.list_members(MagicMock(), group_id=uuid4())

    assert row["name"] == "Ada L."


def test_member_name_is_used_when_there_is_no_profile():
    service = _service([_membership(profile=None, name="Ada")])

    [row] = service.list_members(MagicMock(), group_id=uuid4())

    assert row["name"] == "Ada"


def test_memberships_without_a_member_row_are_skipped():
    orphan = _membership()
    orphan.member = None
    service = _service([orphan, _membership()])

    rows = service.list_members(MagicMock(), group_id=uuid4())

    assert len(rows) == 1
