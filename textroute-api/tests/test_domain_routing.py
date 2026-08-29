"""Domain rules: routing policy, message roles and shapes, status lifecycle."""

from uuid import uuid4

import pytest

from src.domain.message_role import (
    InvalidMessageShapeError,
    MessageKind,
    MessageSenderRole,
    build_message_role,
    determine_inbound_kind,
    is_routable,
)
from src.domain.message_status import (
    MODERATION_QUEUE_STATUSES,
    PRE_DELIVERY_STATUSES,
    TERMINAL_STATUSES,
    MessageWorkflowStatus,
)
from src.domain.routing_policy import RoutingPolicy, requires_moderation

_A = uuid4()
_B = uuid4()


def test_moderator_required_requires_moderation():
    assert requires_moderation(RoutingPolicy.MODERATOR_REQUIRED.value) is True


def test_auto_group_does_not_require_moderation():
    assert requires_moderation(RoutingPolicy.AUTO_GROUP.value) is False


@pytest.mark.parametrize(
    "raw",
    [
        RoutingPolicy.AUTO_MATCHED.value,  # reserved, not implemented
        "something_new",
        "",
        None,
    ],
)
def test_unimplemented_and_unknown_policies_fail_safe(raw):
    """Never fail open into an unreviewed broadcast."""
    assert requires_moderation(raw) is True


def test_joining_an_open_request_is_a_member_reply():
    assert (
        determine_inbound_kind(joins_open_request=True) is MessageKind.MEMBER_REPLY
    )


def test_message_with_no_open_request_starts_one():
    assert (
        determine_inbound_kind(joins_open_request=False)
        is MessageKind.ORIGINAL_REQUEST
    )


def test_only_an_original_request_is_routable():
    """The predicate a routing policy consults, so a reply can never broadcast."""
    assert is_routable(MessageKind.ORIGINAL_REQUEST) is True
    for kind in MessageKind:
        if kind is not MessageKind.ORIGINAL_REQUEST:
            assert is_routable(kind) is False
    assert is_routable(None) is False


@pytest.mark.parametrize(
    "kind, expected_role",
    [
        (MessageKind.ORIGINAL_REQUEST, MessageSenderRole.MEMBER),
        (MessageKind.MEMBER_REPLY, MessageSenderRole.MEMBER),
        (MessageKind.CONFIRMATION, MessageSenderRole.MEMBER),
        (MessageKind.MODERATOR_CLARIFICATION, MessageSenderRole.MODERATOR),
        (MessageKind.FANOUT_COPY, MessageSenderRole.SYSTEM),
    ],
)
def test_each_kind_has_exactly_one_sender_role(kind, expected_role):
    assert build_message_role(
        kind=kind,
        member_id=_A,
        author_member_id=None if kind is MessageKind.FANOUT_COPY else _A,
    )["sender_role"] == expected_role.value


def test_member_authored_kinds_make_author_and_subject_the_same_person():
    shape = build_message_role(kind=MessageKind.MEMBER_REPLY, member_id=_A)
    assert shape["author_member_id"] == _A == shape["member_id"]


def test_a_member_reply_cannot_be_attributed_to_someone_else():
    with pytest.raises(InvalidMessageShapeError):
        build_message_role(
            kind=MessageKind.MEMBER_REPLY,
            member_id=_A,
            author_member_id=_B,
        )


def test_a_fanout_copy_has_no_author():
    """Nobody wrote it: the system reproduced the requester's words verbatim."""
    shape = build_message_role(kind=MessageKind.FANOUT_COPY, member_id=_A)
    assert shape["author_member_id"] is None
    assert shape["member_id"] == _A  # the recipient

    with pytest.raises(InvalidMessageShapeError):
        build_message_role(
            kind=MessageKind.FANOUT_COPY,
            member_id=_A,
            author_member_id=_B,
        )


def test_a_moderator_clarification_records_its_author_and_recipient_separately():
    shape = build_message_role(
        kind=MessageKind.MODERATOR_CLARIFICATION,
        member_id=_A,
        author_member_id=_B,
    )
    assert shape["member_id"] == _A
    assert shape["author_member_id"] == _B

    with pytest.raises(InvalidMessageShapeError):
        build_message_role(
            kind=MessageKind.MODERATOR_CLARIFICATION,
            member_id=_A,
            author_member_id=None,
        )


def test_auto_authorized_is_never_queued_for_a_moderator():
    """Policy-routed messages must not surface as awaiting human review."""
    assert MessageWorkflowStatus.AUTO_AUTHORIZED not in MODERATION_QUEUE_STATUSES


def test_auto_authorized_is_transitional_not_terminal():
    assert MessageWorkflowStatus.AUTO_AUTHORIZED not in TERMINAL_STATUSES


def test_both_routes_are_cleared_for_delivery():
    assert PRE_DELIVERY_STATUSES == {
        MessageWorkflowStatus.APPROVED,
        MessageWorkflowStatus.AUTO_AUTHORIZED,
    }


def test_approval_and_authorization_are_distinct_statuses():
    """The whole point of the split: one implies a human acted, one does not."""
    assert (
        MessageWorkflowStatus.APPROVED.value
        != MessageWorkflowStatus.AUTO_AUTHORIZED.value
    )
