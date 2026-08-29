"""Role stamping at message creation.

The database enforces the same five shapes, but these assert the domain catches
them first, so a bad combination surfaces as a readable error rather than an
IntegrityError from a check constraint.
"""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.managers.message_manager import MessageManager
from src.domain.message_role import InvalidMessageShapeError, MessageKind

GROUP_ID = uuid4()


def _created(db):
    """The Message instance handed to the session."""
    return db.add.call_args.args[0]


def test_inbound_message_is_stamped_with_role_and_author_at_creation():
    db = MagicMock()
    sender_id = uuid4()

    MessageManager().create_inbound(
        db,
        group_id=GROUP_ID,
        member_id=sender_id,
        kind=MessageKind.ORIGINAL_REQUEST,
        request_id=3,
        from_phone_number="+15551112222",
        to_phone_number="+15559876543",
        body="Does anyone have an axe?",
    )

    message = _created(db)
    assert message.kind == "original_request"
    assert message.sender_role == "member"
    # The sender is both subject and author of their own message.
    assert message.member_id == sender_id
    assert message.author_member_id == sender_id
    assert message.request_id == 3
    db.flush.assert_called_once()


def test_fanout_copy_records_its_recipient_and_no_author():
    db = MagicMock()
    recipient_id = uuid4()

    MessageManager().create_outbound(
        db,
        group_id=GROUP_ID,
        member_id=recipient_id,
        kind=MessageKind.FANOUT_COPY,
        request_id=3,
        from_phone_number="+15559876543",
        to_phone_number="+15552223333",
        body="Does anyone have an axe?",
    )

    message = _created(db)
    assert message.kind == "fanout_copy"
    assert message.sender_role == "system"
    assert message.member_id == recipient_id
    # Nobody wrote it: the system reproduced the requester's words.
    assert message.author_member_id is None


def test_moderator_clarification_separates_author_from_recipient():
    db = MagicMock()
    recipient_id = uuid4()
    moderator_id = uuid4()

    MessageManager().create_outbound(
        db,
        group_id=GROUP_ID,
        member_id=recipient_id,
        kind=MessageKind.MODERATOR_CLARIFICATION,
        author_member_id=moderator_id,
        request_id=3,
        from_phone_number="+15559876543",
        to_phone_number="+15552223333",
        body="Which day works for you?",
    )

    message = _created(db)
    assert message.sender_role == "moderator"
    assert message.member_id == recipient_id
    assert message.author_member_id == moderator_id


def test_a_fanout_copy_claiming_an_author_is_refused():
    db = MagicMock()

    with pytest.raises(InvalidMessageShapeError, match="no author"):
        MessageManager().create_outbound(
            db,
            group_id=GROUP_ID,
            member_id=uuid4(),
            kind=MessageKind.FANOUT_COPY,
            author_member_id=uuid4(),
            from_phone_number="+15559876543",
            to_phone_number="+15552223333",
            body="x",
        )
    db.add.assert_not_called()


def test_a_moderator_clarification_without_an_author_is_refused():
    db = MagicMock()

    with pytest.raises(InvalidMessageShapeError):
        MessageManager().create_outbound(
            db,
            group_id=GROUP_ID,
            member_id=uuid4(),
            kind=MessageKind.MODERATOR_CLARIFICATION,
            from_phone_number="+15559876543",
            to_phone_number="+15552223333",
            body="x",
        )
    db.add.assert_not_called()


def test_recording_a_routing_policy_never_revises_the_kind():
    """Kind is stamped once at ingress; only the policy snapshot lands later."""
    db = MagicMock()
    message = MagicMock(kind="original_request")

    MessageManager().record_routing_policy(db, message, routing_policy="auto_group")

    assert message.routing_policy == "auto_group"
    assert message.kind == "original_request"
