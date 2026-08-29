"""Unit tests for moderation approve / reject / fan-out."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call
from uuid import uuid4

import pytest

from src.core.providers.sms_provider import LoggingSmsProvider, SmsProviderError
from src.domain.message_role import MessageKind, RequestEventType
from src.domain.message_status import MessageWorkflowStatus
from src.services.group_service import GroupService
from src.services.messaging_service import MessagingService
from src.services.moderation_service import (
    InvalidModerationStateError,
    InvalidRecipientsError,
    MessageNotFoundError,
    ModerationService,
)


def test_logging_sms_provider_returns_id():
    provider = LoggingSmsProvider()
    sid = provider.send_sms(
        from_number="+15550000001",
        to_number="+15550000002",
        body="hello",
    )
    assert sid.startswith("log_")


def test_messaging_service_persists_after_provider_send():
    db = MagicMock()
    message_mgr = MagicMock()
    outbound = SimpleNamespace(id=uuid4())
    message_mgr.create_outbound.return_value = outbound
    provider = MagicMock()
    provider.send_sms.return_value = "prov_1"

    service = MessagingService(message_manager=message_mgr, sms_provider=provider)
    group = SimpleNamespace(id=uuid4())
    member = SimpleNamespace(id=uuid4(), phone_number="+15551112222")

    result = service.send_message(
        db,
        group=group,
        to_member=member,
        from_phone_number="+15559876543",
        body="Does anyone have a ladder?",
        kind=MessageKind.FANOUT_COPY,
        parent_message_id=uuid4(),
    )

    assert result is outbound
    provider.send_sms.assert_called_once()
    message_mgr.create_outbound.assert_called_once()
    assert (
        message_mgr.create_outbound.call_args.kwargs["body"]
        == "Does anyone have a ladder?"
    )
    assert (
        message_mgr.create_outbound.call_args.kwargs["workflow_status"]
        == MessageWorkflowStatus.SENT.value
    )


def test_messaging_service_provider_failure_does_not_persist():
    db = MagicMock()
    message_mgr = MagicMock()
    provider = MagicMock()
    provider.send_sms.side_effect = SmsProviderError("twilio down")

    service = MessagingService(message_manager=message_mgr, sms_provider=provider)
    with pytest.raises(SmsProviderError, match="twilio down"):
        service.send_message(
            db,
            group=SimpleNamespace(id=uuid4()),
            to_member=SimpleNamespace(id=uuid4(), phone_number="+15551112222"),
            from_phone_number="+15559876543",
            body="hi",
            kind=MessageKind.FANOUT_COPY,
        )
    message_mgr.create_outbound.assert_not_called()


def test_messaging_service_unexpected_errors_are_not_wrapped():
    db = MagicMock()
    message_mgr = MagicMock()
    provider = MagicMock()
    provider.send_sms.side_effect = RuntimeError("bug")

    service = MessagingService(message_manager=message_mgr, sms_provider=provider)
    with pytest.raises(RuntimeError, match="bug"):
        service.send_message(
            db,
            group=SimpleNamespace(id=uuid4()),
            to_member=SimpleNamespace(id=uuid4(), phone_number="+15551112222"),
            from_phone_number="+15559876543",
            body="hi",
            kind=MessageKind.FANOUT_COPY,
        )
    message_mgr.create_outbound.assert_not_called()


def test_approve_records_moderator_decision_then_delegates_fanout():
    """Approval is the moderator's act; delivery belongs to RoutingService."""
    db = MagicMock()
    message_id = uuid4()
    group_id = uuid4()
    sender_id = uuid4()
    recipient_id = uuid4()

    message = SimpleNamespace(
        id=message_id,
        group_id=group_id,
        member_id=sender_id,
        body="Does anyone have a pressure washer I can borrow this weekend?",
        workflow_status=MessageWorkflowStatus.AWAITING_MODERATOR.value,
        group=SimpleNamespace(id=group_id),
        suggested_recipient_ids=[recipient_id],
        routed_recipient_ids=None,
        request_id=44,
        kind="original_request",
        sender_role="member",
        routing_policy="moderator_required",
        intent="request_borrow",
        confidence=0.4,
        constraints={"object": "pressure washer"},
        parent_message_id=None,
        created_at=None,
        processing_notes=None,
    )
    recipient = SimpleNamespace(id=recipient_id, phone_number="+15552222222", name="John")

    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = message

    def apply_approval(db, msg, *, routed_recipient_ids, workflow_status):
        msg.routed_recipient_ids = routed_recipient_ids
        msg.workflow_status = workflow_status
        return msg

    message_mgr.apply_approval.side_effect = apply_approval

    membership_mgr = MagicMock()
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        member=recipient,
        member_id=recipient_id,
    )
    membership_mgr.get_membership.return_value = None

    outbound_id = str(uuid4())
    routing = MagicMock()
    routing.fan_out.return_value = {
        "delivered_outbound_ids": [outbound_id],
        "delivery_failures": [],
    }

    event_mgr = MagicMock()
    service = ModerationService(
        message_manager=message_mgr,
        membership_manager=membership_mgr,
        phone_number_manager=MagicMock(),
        routing_service=routing,
        request_event_manager=event_mgr,
    )

    result = service.approve(
        db,
        message_id,
        group_id=group_id,
        recipient_ids=[recipient_id],
    )

    # Moderator approval is recorded as APPROVED, never auto_authorized.
    assert message.workflow_status == MessageWorkflowStatus.APPROVED.value
    assert message.routed_recipient_ids == [recipient_id]

    # Both routes to delivery write the same event; the payload is where the
    # audit trail distinguishes a person from a policy.
    event = event_mgr.record.call_args.kwargs
    assert event["request_id"] == 44
    assert event["event_type"] is RequestEventType.AUTHORIZED
    assert event["payload"]["by"] == "moderator"

    routing.fan_out.assert_called_once()
    assert routing.fan_out.call_args.args[2] == [recipient]
    assert result["delivered_outbound_ids"] == [outbound_id]
    assert "routed_recipients" in result


def test_approve_rejects_empty_recipients():
    db = MagicMock()
    message = SimpleNamespace(
        id=uuid4(),
        workflow_status=MessageWorkflowStatus.AWAITING_MODERATOR.value,
        member_id=uuid4(),
        group_id=uuid4(),
    )
    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = message
    service = ModerationService(message_manager=message_mgr)

    with pytest.raises(InvalidRecipientsError):
        service.approve(
            db,
            message.id,
            group_id=message.group_id,
            recipient_ids=[],
        )


def test_approve_wrong_state():
    db = MagicMock()
    message = SimpleNamespace(
        id=uuid4(),
        group_id=uuid4(),
        workflow_status=MessageWorkflowStatus.DELIVERED.value,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = message
    service = ModerationService(message_manager=message_mgr)

    with pytest.raises(InvalidModerationStateError):
        service.approve(
            db,
            message.id,
            group_id=message.group_id,
            recipient_ids=[uuid4()],
        )


def test_reject_message():
    db = MagicMock()
    message = SimpleNamespace(
        id=uuid4(),
        group_id=uuid4(),
        member_id=uuid4(),
        body="hi",
        workflow_status=MessageWorkflowStatus.AWAITING_MODERATOR.value,
        intent=None,
        confidence=None,
        constraints=None,
        suggested_recipient_ids=[],
        routed_recipient_ids=None,
        request_id=None,
        kind="original_request",
        sender_role="member",
        routing_policy="moderator_required",
        parent_message_id=None,
        created_at=None,
        processing_notes=None,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = message

    def set_status(db, msg, status, processing_notes=None):
        msg.workflow_status = status
        if processing_notes is not None:
            msg.processing_notes = processing_notes
        return msg

    message_mgr.set_workflow_status.side_effect = set_status
    service = ModerationService(message_manager=message_mgr)

    result = service.reject(db, message.id, group_id=message.group_id)
    assert result["workflow_status"] == MessageWorkflowStatus.MODERATOR_REJECTED.value


def test_cross_group_message_is_not_visible():
    db = MagicMock()
    message = SimpleNamespace(id=uuid4(), group_id=uuid4())
    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = message
    service = ModerationService(message_manager=message_mgr)

    with pytest.raises(MessageNotFoundError, match="Message not found"):
        service.get_message(db, message.id, group_id=uuid4())


def test_queue_asks_only_for_awaiting_moderator():
    """The review queue is the source of truth for the needs-review count."""
    db = MagicMock()
    message_mgr = MagicMock()
    message_mgr.list_inbound_for_group.return_value = []
    ModerationService(message_manager=message_mgr).list_queue(db, uuid4())

    assert message_mgr.list_inbound_for_group.call_args.kwargs["statuses"] == [
        MessageWorkflowStatus.AWAITING_MODERATOR.value
    ]


def test_policy_change_writes_only_the_group_row():
    """Switching a group to auto_group must not rewrite pending messages.

    The per-message routing_policy snapshot exists precisely so history stays
    truthful; a message queued under moderator_required keeps waiting for a
    human even after the group flips to automatic.
    """
    db = MagicMock()
    group = SimpleNamespace(
        id=uuid4(),
        name="Neighbors",
        description=None,
        status="active",
        routing_policy="moderator_required",
    )
    group_mgr = MagicMock()
    group_mgr.get_group.return_value = group

    GroupService(group_manager=group_mgr).set_routing_policy(
        db, group.id, routing_policy="auto_group"
    )

    assert group.routing_policy == "auto_group"
    # Only the group row was written — no message rows were touched.
    assert db.add.call_args_list == [call(group)]
    db.query.assert_not_called()


def test_approve_ignores_the_groups_current_policy():
    """A pending message is approved on its own snapshot, not today's setting."""
    db = MagicMock()
    message_id = uuid4()
    group_id = uuid4()
    recipient_id = uuid4()
    recipient = SimpleNamespace(id=recipient_id, phone_number="+15552222222", name="A")

    message = SimpleNamespace(
        id=message_id,
        group_id=group_id,
        member_id=uuid4(),
        body="Does anyone have an axe?",
        workflow_status=MessageWorkflowStatus.AWAITING_MODERATOR.value,
        # Group has since moved to auto_group; this snapshot must still govern.
        routing_policy="moderator_required",
        kind="original_request",
        sender_role="member",
        group=SimpleNamespace(id=group_id, routing_policy="auto_group"),
        suggested_recipient_ids=[recipient_id],
        routed_recipient_ids=None,
        request_id=None,
        intent=None,
        confidence=None,
        constraints=None,
        parent_message_id=None,
        created_at=None,
        processing_notes=None,
    )

    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = message

    def apply_approval(db, msg, *, routed_recipient_ids, workflow_status):
        msg.routed_recipient_ids = routed_recipient_ids
        msg.workflow_status = workflow_status
        return msg

    message_mgr.apply_approval.side_effect = apply_approval

    membership_mgr = MagicMock()
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        member=recipient, member_id=recipient_id
    )
    membership_mgr.get_membership.return_value = None

    routing = MagicMock()
    routing.fan_out.return_value = {
        "delivered_outbound_ids": [str(uuid4())],
        "delivery_failures": [],
    }

    ModerationService(
        message_manager=message_mgr,
        membership_manager=membership_mgr,
        phone_number_manager=MagicMock(),
        routing_service=routing,
    ).approve(db, message_id, group_id=group_id, recipient_ids=[recipient_id])

    # Moderator approval, not auto-authorization, despite the group's new policy.
    assert message.workflow_status == MessageWorkflowStatus.APPROVED.value
    assert message.routing_policy == "moderator_required"
    message_mgr.apply_routing_authorization.assert_not_called()


def test_list_messages_does_not_filter_by_status():
    """The message list is a feed, not a queue: every workflow state belongs."""
    db = MagicMock()
    message_mgr = MagicMock()
    message_mgr.list_inbound_for_group.return_value = []
    ModerationService(message_manager=message_mgr).list_messages(db, uuid4())

    kwargs = message_mgr.list_inbound_for_group.call_args.kwargs
    assert "statuses" not in kwargs or kwargs["statuses"] is None
