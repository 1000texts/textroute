"""Domain rules: routing policy fallbacks, message kind, status lifecycle."""

import pytest

from src.domain.message_kind import InboundMessageKind, determine_inbound_kind
from src.domain.message_status import (
    MODERATION_QUEUE_STATUSES,
    PRE_DELIVERY_STATUSES,
    TERMINAL_STATUSES,
    MessageWorkflowStatus,
)
from src.domain.routing_policy import RoutingPolicy, requires_moderation


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


def test_original_request_candidate_determines_reply():
    assert (
        determine_inbound_kind(has_original_request_candidate=True)
        is InboundMessageKind.REPLY
    )


def test_no_original_request_candidate_determines_new_request():
    assert (
        determine_inbound_kind(has_original_request_candidate=False)
        is InboundMessageKind.NEW_REQUEST
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
