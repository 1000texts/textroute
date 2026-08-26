"""Unit tests for inbound message routing workflow."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.message_processor import ProcessingResult
from src.core.phone_normalize import InvalidPhoneNumberError, normalize_phone_number
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
    messaging_service=None,
) -> InboundMessageService:
    return InboundMessageService(
        phone_number_manager=phone_number_manager or MagicMock(),
        membership_manager=membership_manager or MagicMock(),
        message_manager=message_manager or MagicMock(),
        message_processor=message_processor or MagicMock(),
        messaging_service=messaging_service or MagicMock(),
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


def test_successful_inbound_message():
    db = MagicMock()
    group_id = uuid4()
    member_id = uuid4()
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
    message = SimpleNamespace(id=message_id)

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = receiving

    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = member
    membership_mgr.get_active_membership.return_value = membership

    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.create_inbound.return_value = message

    processor = MagicMock()
    processor.process.return_value = ProcessingResult(notes="noop")

    messaging = MagicMock()

    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        messaging_service=messaging,
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
    message_mgr.create_inbound.assert_called_once()
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


def test_processor_failure_keeps_persisted_message():
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

    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.create_inbound.return_value = SimpleNamespace(id=message_id)

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
    assert db.commit.call_count == 1
    db.rollback.assert_called()
