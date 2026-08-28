"""Unit tests for shared fan-out: status bookkeeping and partial failure."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.providers.sms_provider import SmsProviderError
from src.domain.message_status import MessageWorkflowStatus
from src.services.routing_service import RoutingError, RoutingService


def _message(status: str, group_id, **overrides):
    base = dict(
        id=uuid4(),
        group_id=group_id,
        member_id=uuid4(),
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

    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=messaging,
    )
    result = service.fan_out(db, message, [recipient])

    assert message.workflow_status == MessageWorkflowStatus.DELIVERED.value
    assert result["delivered_outbound_ids"] == [str(outbound.id)]
    # The inbound body is forwarded unchanged, parented to the original request.
    assert messaging.send_message.call_args.kwargs["body"] == message.body
    assert messaging.send_message.call_args.kwargs["parent_message_id"] == message.id


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

    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=messaging,
    )
    result = service.fan_out(db, message, [good, bad])

    assert message.workflow_status == MessageWorkflowStatus.PARTIALLY_DELIVERED.value
    assert result["delivered_outbound_ids"] == [str(outbound.id)]
    assert len(result["delivery_failures"]) == 1


def test_fan_out_total_failure_sets_delivery_failed():
    db = MagicMock()
    group_id = uuid4()
    message = _message(MessageWorkflowStatus.AUTO_AUTHORIZED.value, group_id)
    recipient = SimpleNamespace(id=uuid4(), phone_number="+15552222222", name="A")

    message_mgr, phone_mgr = _managers()
    messaging = MagicMock()
    messaging.send_message.side_effect = SmsProviderError("provider down")

    service = RoutingService(
        message_manager=message_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=messaging,
    )
    result = service.fan_out(db, message, [recipient])

    assert message.workflow_status == MessageWorkflowStatus.DELIVERY_FAILED.value
    assert result["delivered_outbound_ids"] == []
    assert len(result["delivery_failures"]) == 1


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
