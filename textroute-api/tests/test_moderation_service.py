"""Unit tests for moderation approve / reject / fan-out."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.sms_provider import LoggingSmsProvider, SmsProviderError
from src.domain.message_status import MessageWorkflowStatus
from src.services.messaging_service import MessagingService
from src.services.moderation_service import (
    InvalidModerationStateError,
    InvalidRecipientsError,
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
        parent_message_id=uuid4(),
    )

    assert result is outbound
    provider.send_sms.assert_called_once()
    message_mgr.create_outbound.assert_called_once()
    assert (
        message_mgr.create_outbound.call_args.kwargs["body"]
        == "Does anyone have a ladder?"
    )


def test_messaging_service_provider_failure_does_not_persist():
    db = MagicMock()
    message_mgr = MagicMock()
    provider = MagicMock()
    provider.send_sms.side_effect = RuntimeError("twilio down")

    service = MessagingService(message_manager=message_mgr, sms_provider=provider)
    with pytest.raises(SmsProviderError):
        service.send_message(
            db,
            group=SimpleNamespace(id=uuid4()),
            to_member=SimpleNamespace(id=uuid4(), phone_number="+15551112222"),
            from_phone_number="+15559876543",
            body="hi",
        )
    message_mgr.create_outbound.assert_not_called()


def test_approve_fans_out_original_body():
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
        approved_recipient_ids=None,
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

    def apply_approval(db, msg, *, approved_recipient_ids, workflow_status):
        msg.approved_recipient_ids = approved_recipient_ids
        msg.workflow_status = workflow_status
        return msg

    def set_status(db, msg, status, processing_notes=None):
        msg.workflow_status = status
        if processing_notes is not None:
            msg.processing_notes = processing_notes
        return msg

    message_mgr.apply_approval.side_effect = apply_approval
    message_mgr.set_workflow_status.side_effect = set_status

    membership_mgr = MagicMock()
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        member=recipient,
        member_id=recipient_id,
    )

    phone_mgr = MagicMock()
    phone_mgr.list_for_group.return_value = [
        SimpleNamespace(status="assigned", phone_number="+15559876543")
    ]

    messaging = MagicMock()
    outbound = SimpleNamespace(id=uuid4())
    messaging.send_message.return_value = outbound

    service = ModerationService(
        message_manager=message_mgr,
        membership_manager=membership_mgr,
        phone_number_manager=phone_mgr,
        messaging_service=messaging,
    )

    result = service.approve(db, message_id, recipient_ids=[recipient_id])

    messaging.send_message.assert_called_once()
    call_kwargs = messaging.send_message.call_args.kwargs
    assert call_kwargs["body"] == message.body
    assert call_kwargs["parent_message_id"] == message_id
    assert result["workflow_status"] == MessageWorkflowStatus.DELIVERED.value
    assert result["delivered_outbound_ids"] == [str(outbound.id)]


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
        service.approve(db, message.id, recipient_ids=[])


def test_approve_wrong_state():
    db = MagicMock()
    message = SimpleNamespace(
        id=uuid4(),
        workflow_status=MessageWorkflowStatus.DELIVERED.value,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = message
    service = ModerationService(message_manager=message_mgr)

    with pytest.raises(InvalidModerationStateError):
        service.approve(db, message.id, recipient_ids=[uuid4()])


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
        approved_recipient_ids=None,
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

    result = service.reject(db, message.id)
    assert result["workflow_status"] == MessageWorkflowStatus.MODERATOR_REJECTED.value
