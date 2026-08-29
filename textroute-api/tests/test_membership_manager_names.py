"""How ``members.name`` is set when a member is looked up or created.

A phone number can be enrolled more than once, by different people, so the
overwrite rule matters: a later careless entry must not silently rename someone.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.core.managers.membership_manager import MembershipManager


def _db_returning(member):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = member
    return db


def test_name_is_set_when_the_member_is_created():
    db = _db_returning(None)

    member = MembershipManager().get_or_create_by_phone(
        db,
        "+1 555 123 4567",
        name="Ada",
    )

    assert member.name == "Ada"
    # Normalized to E.164 before persisting.
    assert member.phone_number == "+15551234567"
    db.add.assert_called_once_with(member)


def test_a_missing_name_is_backfilled_on_an_existing_member():
    existing = SimpleNamespace(phone_number="+15551234567", name=None)
    db = _db_returning(existing)

    member = MembershipManager().get_or_create_by_phone(
        db,
        "+15551234567",
        name="Ada",
    )

    assert member.name == "Ada"


def test_an_existing_name_is_never_overwritten():
    existing = SimpleNamespace(phone_number="+15551234567", name="Ada")
    db = _db_returning(existing)

    member = MembershipManager().get_or_create_by_phone(
        db,
        "+15551234567",
        name="Someone Else",
    )

    assert member.name == "Ada"
    db.add.assert_not_called()


def test_omitting_the_name_still_works():
    """Callers that have no name, such as an inbound SMS from a new number."""
    db = _db_returning(None)

    member = MembershipManager().get_or_create_by_phone(db, "+15551234567")

    assert member.name is None
