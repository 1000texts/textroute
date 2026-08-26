"""Unit tests for inbound message routing workflow."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.message_processor import MemberContext, MessageProcessor, ProcessingResult
from src.core.phone_normalize import InvalidPhoneNumberError, normalize_phone_number
from src.domain.message_status import MessageWorkflowStatus
from src.services.inbound_errors import (
    DuplicateInboundMessageError,
    SenderNotInGroupError,
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
    UnknownSenderError,
)
from src.services.inbound_message_service import InboundMessageService


def _service(
    *,
    phone_number_manager=None,
    membership_manager=None,
    message_manager=None,
    message_processor=None,
) -> InboundMessageService:
    return InboundMessageService(
        phone_number_manager=phone_number_manager or MagicMock(),
        membership_manager=membership_manager or MagicMock(),
        message_manager=message_manager or MagicMock(),
        message_processor=message_processor or MagicMock(),
    )


def test_normalize_phone_number_us_formats():
    assert normalize_phone_number("+1 555 123 4567") == "+15551234567"
    assert normalize_phone_number("(555) 123-4567") == "+15551234567"
    assert normalize_phone_number("15551234567") == "+15551234567"
    assert normalize_phone_number("+15551234567") == "+15551234567"


def test_normalize_phone_number_invalid():
    with pytest.raises(InvalidPhoneNumberError):
        normalize_phone_number("")
    with pytest.raises(InvalidPhoneNumberError):
        normalize_phone_number("abc")


def test_message_processor_borrow_heuristic():
    sender = uuid4()
    other = uuid4()
    processor = MessageProcessor()
    result = processor.process(
        message_body="Does anyone have a pressure washer I can borrow this weekend?",
        sender_id=sender,
        candidates=[
            MemberContext(id=sender, phone_number="+15551111111", name="Kenji"),
            MemberContext(id=other, phone_number="+15552222222", name="John"),
        ],
    )
    assert result.intent == "request_borrow"
    assert result.suggested_recipient_ids == [other]
    assert "pressure" in (result.constraints.get("object") or "")
    assert result.constraints.get("time_constraint") == "this weekend"


def test_successful_inbound_message_awaits_moderator():
    db = MagicMock()
    group_id = uuid4()
    member_id = uuid4()
    other_id = uuid4()
    message_id = uuid4()

    receiving = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id),
    )
    member = SimpleNamespace(id=member_id, phone_number="+15551234567")
    membership = SimpleNamespace(id=uuid4())
    message = SimpleNamespace(
        id=message_id,
        body="Does anyone have a ladder?",
        member_id=member_id,
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
    )

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = receiving

    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = member
    membership_mgr.get_active_membership.return_value = membership
    membership_mgr.list_active_memberships.return_value = [
        SimpleNamespace(
            member=SimpleNamespace(id=member_id, phone_number="+15551234567", name="A"),
            role="member",
            member_id=member_id,
        ),
        SimpleNamespace(
            member=SimpleNamespace(id=other_id, phone_number="+15550001111", name="B"),
            role="member",
            member_id=other_id,
        ),
    ]

    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.find_recent_fanout_to_member.return_value = None
    message_mgr.create_inbound.return_value = message

    processor = MagicMock()
    processor.process.return_value = ProcessingResult(
        intent="request_borrow",
        suggested_recipient_ids=[other_id],
        confidence=0.4,
        notes="heuristic_v1_suggest_active_members",
    )

    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Does anyone have a ladder?",
        provider_message_id="SM123",
    )

    assert result["status"] == "ok"
    assert result["message_id"] == str(message_id)
    assert result["intent"] == "request_borrow"
    message_mgr.create_inbound.assert_called_once()
    message_mgr.apply_processing_result.assert_called_once()
    processor.process.assert_called_once()
    assert db.commit.call_count == 2


def test_unknown_receiving_number():
    db = MagicMock()
    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = None
    service = _service(phone_number_manager=phone_mgr)

    with pytest.raises(UnknownReceivingNumberError):
        service.handle_incoming_message(
            db,
            from_phone_number="+15551234567",
            to_phone_number="+15550000000",
            body="hello",
        )


def test_unassigned_receiving_number():
    db = MagicMock()
    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=None,
        status="available",
        group=None,
    )
    service = _service(phone_number_manager=phone_mgr)

    with pytest.raises(UnassignedPhoneNumberError):
        service.handle_incoming_message(
            db,
            from_phone_number="+15551234567",
            to_phone_number="+15559876543",
            body="hello",
        )


def test_unknown_sender():
    db = MagicMock()
    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=uuid4(),
        status="assigned",
        group=SimpleNamespace(id=uuid4()),
    )
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = None
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
    )

    with pytest.raises(UnknownSenderError):
        service.handle_incoming_message(
            db,
            from_phone_number="+15551234567",
            to_phone_number="+15559876543",
            body="hello",
        )


def test_sender_not_in_group():
    db = MagicMock()
    group_id = uuid4()
    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id),
    )
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=uuid4(), phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = None
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
    )

    with pytest.raises(SenderNotInGroupError):
        service.handle_incoming_message(
            db,
            from_phone_number="+15551234567",
            to_phone_number="+15559876543",
            body="hello",
        )


def test_duplicate_provider_message():
    db = MagicMock()
    existing_id = uuid4()
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = SimpleNamespace(
        id=existing_id
    )
    service = _service(message_manager=message_mgr)

    with pytest.raises(DuplicateInboundMessageError) as exc:
        service.handle_incoming_message(
            db,
            from_phone_number="+15551234567",
            to_phone_number="+15559876543",
            body="hello",
            provider_message_id="SM_DUP",
        )

    assert exc.value.message_id == str(existing_id)
    message_mgr.create_inbound.assert_not_called()


def test_processor_failure_marks_processing_failed():
    db = MagicMock()
    group_id = uuid4()
    message_id = uuid4()

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id),
    )

    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=uuid4(), phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(id=uuid4())
    membership_mgr.list_active_memberships.return_value = []

    message = SimpleNamespace(id=message_id, body="hello", member_id=uuid4())
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.find_recent_fanout_to_member.return_value = None
    message_mgr.create_inbound.return_value = message
    message_mgr.find_by_id.return_value = message

    processor = MagicMock()
    processor.process.side_effect = RuntimeError("AI down")

    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="hello",
    )

    assert result["status"] == "persisted"
    assert result["message_id"] == str(message_id)
    assert result["processing"] == "failed"
    assert result["workflow_status"] == MessageWorkflowStatus.PROCESSING_FAILED.value
    message_mgr.set_workflow_status.assert_called()
    db.rollback.assert_called()


def test_reply_to_fanout_is_persisted_without_processing():
    db = MagicMock()
    group_id = uuid4()
    member_id = uuid4()
    message_id = uuid4()
    parent_id = uuid4()

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id),
    )
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=member_id, phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(id=uuid4())

    message = SimpleNamespace(
        id=message_id,
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.find_recent_fanout_to_member.return_value = SimpleNamespace(
        id=uuid4(),
        parent_message_id=parent_id,
    )
    message_mgr.create_inbound.return_value = message

    processor = MagicMock()
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Yeah, Saturday morning works.",
    )

    assert result["processing"] == "reply_persisted"
    assert result["parent_message_id"] == str(parent_id)
    processor.process.assert_not_called()
