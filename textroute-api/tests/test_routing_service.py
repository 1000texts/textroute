"""Unit tests for shared fan-out: status bookkeeping and partial failure."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.providers.sms_provider import SmsProviderError
from src.domain.message_role import MessageKind
from src.domain.message_status import MessageWorkflowStatus
from src.services.routing_service import RoutingError, RoutingService


def _message(status: str, group_id, **overrides):
    base = dict(
        id=uuid4(),
        group_id=group_id,
        member_id=uuid4(),
        request_id=42,
        body="Does anyone have a ladder?",
        workflow_status=status,
        group=SimpleNamespace(id=group_id),
        processing_notes=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _managers():
    message_mgr = MagicMock()

    def set_status(db, msg, status, processing_notes=None):
        msg.workflow_status = status
        if processing_notes is not None:
            msg.processing_notes = processing_notes
        return msg

    message_mgr.set_workflow_status.side_effect = set_status

    phone_mgr = MagicMock()
    phone_mgr.list_for_group.return_value = [
        SimpleNamespace(status="assigned", phone_number="+15559876543")
    ]
    return message_mgr, phone_mgr


def _recorded_events(event_mgr) -> list[str]:
    return [c.kwargs["event_type"].value for c in event_mgr.record.call_args_list]


@pytest.mark.parametrize(
    "status",
    [
        MessageWorkflowStatus.APPROVED.value,
        MessageWorkflowStatus.AUTO_AUTHORIZED.value,
    ],
)
def test_fan_out_accepts_both_routes_to_delivery(status):
    """Moderator-approved and policy-authorized messages are both deliverable."""
    db = MagicMock()
    group_id = uuid4()
    message = _message(status, group_id)
    recipient = SimpleNamespace(id=uuid4(), phone_number="+15552222222", name="A")

    message_mgr, phone_mgr = _managers()
    messaging = MagicMock()
    outbound = SimpleNamespace(id=uuid4())
    messaging.send_message.return_value = outbound

    event_mgr = MagicMock()
    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=messaging,
        request_event_manager=event_mgr,
    )
    result = service.fan_out(db, message, [recipient])

    assert message.workflow_status == MessageWorkflowStatus.DELIVERED.value
    assert result["delivered_outbound_ids"] == [str(outbound.id)]
    # The inbound body is forwarded unchanged, parented to the original request
    # and carried into the same request thread.
    sent = messaging.send_message.call_args.kwargs
    assert sent["body"] == message.body
    assert sent["parent_message_id"] == message.id
    assert sent["request_id"] == message.request_id
    # A copy is a system artefact: recipient in member_id, nobody as author.
    assert sent["kind"] is MessageKind.FANOUT_COPY
    assert sent["to_member"] is recipient
    assert sent.get("author_member_id") is None

    assert _recorded_events(event_mgr) == ["delivered"]


def test_fan_out_rejects_message_not_cleared_for_delivery():
    db = MagicMock()
    group_id = uuid4()
    message = _message(MessageWorkflowStatus.AWAITING_MODERATOR.value, group_id)
    message_mgr, phone_mgr = _managers()

    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=MagicMock(),
    )

    with pytest.raises(RoutingError, match="not cleared for delivery"):
        service.fan_out(db, message, [SimpleNamespace(id=uuid4())])


def test_fan_out_partial_failure_sets_partially_delivered():
    db = MagicMock()
    group_id = uuid4()
    message = _message(MessageWorkflowStatus.APPROVED.value, group_id)
    good = SimpleNamespace(id=uuid4(), phone_number="+15552222222", name="A")
    bad = SimpleNamespace(id=uuid4(), phone_number="+15553333333", name="B")

    message_mgr, phone_mgr = _managers()
    messaging = MagicMock()
    outbound = SimpleNamespace(id=uuid4())

    def send_message(db, **kwargs):
        if kwargs["to_member"].id == bad.id:
            raise SmsProviderError("provider down")
        return outbound

    messaging.send_message.side_effect = send_message

    event_mgr = MagicMock()
    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=messaging,
        request_event_manager=event_mgr,
    )
    result = service.fan_out(db, message, [good, bad])

    assert message.workflow_status == MessageWorkflowStatus.PARTIALLY_DELIVERED.value
    assert result["delivered_outbound_ids"] == [str(outbound.id)]
    assert len(result["delivery_failures"]) == 1

    # A partial fan-out is a mix of per-recipient outcomes, never its own event
    # type: the aggregate lives on the message and is not stored twice.
    assert _recorded_events(event_mgr) == ["delivered", "delivery_failed"]
    failed = event_mgr.record.call_args_list[1].kwargs
    assert failed["payload"]["member_id"] == str(bad.id)
    # Nothing was sent, so there is no outbound row for the event to point at.
    assert failed["message_id"] is None


def test_fan_out_total_failure_sets_delivery_failed():
    db = MagicMock()
    group_id = uuid4()
    message = _message(MessageWorkflowStatus.AUTO_AUTHORIZED.value, group_id)
    recipient = SimpleNamespace(id=uuid4(), phone_number="+15552222222", name="A")

    message_mgr, phone_mgr = _managers()
    messaging = MagicMock()
    messaging.send_message.side_effect = SmsProviderError("provider down")

    event_mgr = MagicMock()
    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=messaging,
        request_event_manager=event_mgr,
    )
    result = service.fan_out(db, message, [recipient])

    assert message.workflow_status == MessageWorkflowStatus.DELIVERY_FAILED.value
    assert result["delivered_outbound_ids"] == []
    assert len(result["delivery_failures"]) == 1
    assert _recorded_events(event_mgr) == ["delivery_failed"]


def test_fan_out_requires_assigned_group_number():
    db = MagicMock()
    group_id = uuid4()
    message = _message(MessageWorkflowStatus.APPROVED.value, group_id)

    message_mgr, phone_mgr = _managers()
    phone_mgr.list_for_group.return_value = []

    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=MagicMock(),
    )

    with pytest.raises(RoutingError, match="no assigned TextRoute number"):
        service.fan_out(db, message, [SimpleNamespace(id=uuid4())])
