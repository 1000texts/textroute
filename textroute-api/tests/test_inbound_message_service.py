"""Unit tests for inbound message routing workflow."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.core.processors.message_processor import (
    MemberContext,
    MessageProcessor,
    ProcessingResult,
)
from src.core.phone_normalize import InvalidPhoneNumberError, normalize_phone_number
from src.domain.message_role import MessageKind, RequestEventType
from src.domain.message_status import MessageWorkflowStatus
from src.services.inbound_errors import (
    DuplicateInboundMessageError,
    SenderNotInGroupError,
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
    UnknownSenderError,
)
from src.services.inbound_message_service import InboundMessageService


def _request_manager(open_request=None, *, new_request_id=1):
    """A request manager that finds ``open_request`` (default: none) for a sender.

    Defaulting to "no open request" matters: a bare MagicMock returns a truthy
    object from every lookup, which would silently make every test a reply.
    """
    mgr = MagicMock()
    mgr.find_open_for_requester.return_value = open_request
    mgr.find_open_for_participant.return_value = None
    mgr.create.return_value = SimpleNamespace(
        id=new_request_id,
        original_message_id=None,
    )
    return mgr


def _service(
    *,
    phone_number_manager=None,
    membership_manager=None,
    message_manager=None,
    message_processor=None,
    routing_service=None,
    request_manager=None,
    request_event_manager=None,
) -> InboundMessageService:
    return InboundMessageService(
        phone_number_manager=phone_number_manager or MagicMock(),
        membership_manager=membership_manager or MagicMock(),
        message_manager=message_manager or MagicMock(),
        message_processor=message_processor or MagicMock(),
        routing_service=routing_service or MagicMock(),
        request_manager=request_manager or _request_manager(),
        request_event_manager=request_event_manager or MagicMock(),
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
        group=SimpleNamespace(id=group_id, routing_policy="moderator_required"),
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
    message_mgr.create_inbound.return_value = message

    processor = MagicMock()
    processor.process.return_value = ProcessingResult(
        intent="request_borrow",
        suggested_recipient_ids=[other_id],
        confidence=0.4,
        notes="heuristic_v1_suggest_active_members",
    )

    request_mgr = _request_manager(new_request_id=7)
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        request_manager=request_mgr,
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
    assert result["request_id"] == 7
    message_mgr.create_inbound.assert_called_once()
    # The request is the parent, and the message is stamped into it at ingress.
    created = message_mgr.create_inbound.call_args.kwargs
    assert created["request_id"] == 7
    assert created["kind"] is MessageKind.ORIGINAL_REQUEST
    # Circular FK closed only once the message exists.
    request_mgr.set_original_message.assert_called_once()
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
        group=SimpleNamespace(id=group_id, routing_policy="moderator_required"),
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


def test_concurrent_duplicate_provider_message():
    db = MagicMock()
    group_id = uuid4()
    existing_id = uuid4()

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id, routing_policy="moderator_required"),
    )

    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=uuid4(), phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(id=uuid4())

    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.side_effect = [
        None,
        SimpleNamespace(id=existing_id),
    ]
    message_mgr.create_inbound.side_effect = IntegrityError(
        "duplicate provider message id",
        params={},
        orig=Exception("unique constraint violation"),
    )

    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
    )

    with pytest.raises(DuplicateInboundMessageError) as exc:
        service.handle_incoming_message(
            db,
            from_phone_number="+15551234567",
            to_phone_number="+15559876543",
            body="hello",
            provider_message_id="SM_RACE",
        )

    assert exc.value.message_id == str(existing_id)
    assert message_mgr.find_by_provider_message_id.call_count == 2
    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_unrelated_integrity_error_is_not_reported_as_duplicate():
    db = MagicMock()
    group_id = uuid4()

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id, routing_policy="moderator_required"),
    )

    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=uuid4(), phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(id=uuid4())

    integrity_error = IntegrityError(
        "foreign key violation",
        params={},
        orig=Exception("unrelated integrity error"),
    )
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.side_effect = [None, None]
    message_mgr.create_inbound.side_effect = integrity_error

    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
    )

    with pytest.raises(IntegrityError) as exc:
        service.handle_incoming_message(
            db,
            from_phone_number="+15551234567",
            to_phone_number="+15559876543",
            body="hello",
            provider_message_id="SM_NOT_DUP",
        )

    assert exc.value is integrity_error
    db.rollback.assert_called_once()
    db.commit.assert_not_called()

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
        group=SimpleNamespace(id=group_id, routing_policy="moderator_required"),
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


def test_reply_into_an_open_request_is_recorded_without_processing():
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
        group=SimpleNamespace(id=group_id, routing_policy="moderator_required"),
    )
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=member_id, phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(id=uuid4())

    message = SimpleNamespace(
        id=message_id,
        parent_message_id=parent_id,
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.create_inbound.return_value = message

    # The member is answering a request that reached them, found through that
    # request's fan-out copy rather than a time window.
    open_request = SimpleNamespace(id=11, original_message_id=parent_id)
    request_mgr = _request_manager()
    request_mgr.find_open_for_participant.return_value = open_request

    processor = MagicMock()
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        request_manager=request_mgr,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Yeah, Saturday morning works.",
    )

    assert result["kind"] == "member_reply"
    assert result["processing"] == "reply_recorded"
    assert result["request_id"] == 11
    assert result["parent_message_id"] == str(parent_id)
    processor.process.assert_not_called()

    created = message_mgr.create_inbound.call_args.kwargs
    assert created["kind"] is MessageKind.MEMBER_REPLY
    # Joins the existing request rather than opening a second one.
    assert created["request_id"] == 11
    request_mgr.create.assert_not_called()
    # The message-graph edge still points at the original request, not at the
    # per-recipient fan-out copy, keeping the star topology.
    assert created["parent_message_id"] == parent_id


def test_a_senders_own_open_request_takes_precedence():
    """A requester's follow-up joins their own request, not one they received."""
    db = MagicMock()
    group_id = uuid4()
    member_id = uuid4()

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id, routing_policy="moderator_required"),
    )
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=member_id, phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(id=uuid4())

    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.create_inbound.return_value = SimpleNamespace(
        id=uuid4(),
        parent_message_id=None,
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
    )

    own = SimpleNamespace(id=5, original_message_id=uuid4())
    someone_elses = SimpleNamespace(id=9, original_message_id=uuid4())
    request_mgr = _request_manager(own)
    request_mgr.find_open_for_participant.return_value = someone_elses

    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        request_manager=request_mgr,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Actually, Sunday would work too.",
    )

    assert result["request_id"] == 5
    request_mgr.find_open_for_participant.assert_not_called()


# ---------------------------------------------------------------------------
# Kind x policy: the central invariant. Kind selects the workflow; the group
# routing policy applies to an original_request only. Belonging to a request is
# parentage, never a moderation decision.
# ---------------------------------------------------------------------------


def _routing_fixtures(*, routing_policy, open_request=None):
    group_id = uuid4()
    member_id = uuid4()
    other_id = uuid4()

    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id, routing_policy=routing_policy),
    )

    other = SimpleNamespace(id=other_id, phone_number="+15550001111", name="B")
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=member_id, phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        id=uuid4(), member=other, member_id=other_id
    )
    membership_mgr.list_active_memberships.return_value = [
        SimpleNamespace(member=other, role="member", member_id=other_id),
    ]

    message = SimpleNamespace(
        id=uuid4(),
        request_id=open_request.id if open_request is not None else 1,
        body="Does anyone have an axe I can borrow?",
        member_id=member_id,
        parent_message_id=(
            open_request.original_message_id if open_request is not None else None
        ),
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.create_inbound.return_value = message

    request_mgr = _request_manager()
    request_mgr.find_open_for_participant.return_value = open_request

    processor = MagicMock()
    processor.process.return_value = ProcessingResult(
        intent="request_borrow",
        suggested_recipient_ids=[other_id],
        confidence=0.4,
        notes="heuristic_v1_suggest_active_members",
    )

    routing = MagicMock()
    routing.fan_out.return_value = {
        "delivered_outbound_ids": [str(uuid4())],
        "delivery_failures": [],
    }
    return (
        phone_mgr,
        membership_mgr,
        message_mgr,
        processor,
        routing,
        other,
        request_mgr,
    )


def test_new_request_under_auto_group_is_routed_automatically():
    db = MagicMock()
    phone_mgr, membership_mgr, message_mgr, processor, routing, other, request_mgr = (
        _routing_fixtures(routing_policy="auto_group")
    )
    event_mgr = MagicMock()
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        routing_service=routing,
        request_manager=request_mgr,
        request_event_manager=event_mgr,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Does anyone have an axe I can borrow?",
    )

    routing.fan_out.assert_called_once()
    assert routing.fan_out.call_args.args[2] == [other]
    assert result["kind"] == "original_request"
    assert result["routing_policy"] == "auto_group"
    assert result["processing"] == "auto_group_authorized"
    # Policy authorized routing; no moderator approved it.
    message_mgr.apply_routing_authorization.assert_called_once()
    message_mgr.apply_approval.assert_not_called()
    # ...and the audit trail says so, rather than naming a person.
    event = event_mgr.record.call_args.kwargs
    assert event["event_type"] is RequestEventType.AUTHORIZED
    assert event["payload"]["by"] == "policy_auto_group"


def test_reply_under_auto_group_is_never_broadcast():
    """Bob's "I have one." must not be fanned out to the whole group."""
    db = MagicMock()
    open_request = SimpleNamespace(id=3, original_message_id=uuid4())
    phone_mgr, membership_mgr, message_mgr, processor, routing, _, request_mgr = (
        _routing_fixtures(routing_policy="auto_group", open_request=open_request)
    )
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        routing_service=routing,
        request_manager=request_mgr,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="I have one.",
    )

    routing.fan_out.assert_not_called()
    processor.process.assert_not_called()
    message_mgr.apply_routing_authorization.assert_not_called()
    assert result["kind"] == "member_reply"
    # Policy is not even consulted for replies, so no snapshot is recorded.
    assert "routing_policy" not in result
    message_mgr.record_routing_policy.assert_not_called()


def test_reply_under_moderator_required_behaves_identically():
    """Reply handling is a slice-level policy, not something the group policy controls."""
    db = MagicMock()
    open_request = SimpleNamespace(id=3, original_message_id=uuid4())
    phone_mgr, membership_mgr, message_mgr, processor, routing, _, request_mgr = (
        _routing_fixtures(
            routing_policy="moderator_required", open_request=open_request
        )
    )
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        routing_service=routing,
        request_manager=request_mgr,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="I have one.",
    )

    routing.fan_out.assert_not_called()
    processor.process.assert_not_called()
    assert result["kind"] == "member_reply"
    assert result["processing"] == "reply_recorded"


def test_auto_matched_falls_back_to_moderation():
    db = MagicMock()
    phone_mgr, membership_mgr, message_mgr, processor, routing, _, request_mgr = (
        _routing_fixtures(routing_policy="auto_matched")
    )
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        routing_service=routing,
        request_manager=request_mgr,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Does anyone have an axe?",
    )

    routing.fan_out.assert_not_called()
    assert result["kind"] == "original_request"
    # Snapshot still records what the group was set to at the time.
    assert result["routing_policy"] == "auto_matched"


def test_auto_group_with_no_eligible_recipients_skips_fanout():
    db = MagicMock()
    phone_mgr, membership_mgr, message_mgr, processor, routing, other, request_mgr = (
        _routing_fixtures(routing_policy="auto_group")
    )

    # The sender is still an active member; the suggested recipient's membership
    # lapsed between suggestion and send, leaving nobody to route to.
    sender_membership = SimpleNamespace(id=uuid4())

    def get_active_membership(db, member_id, group_id):
        return None if member_id == other.id else sender_membership

    membership_mgr.get_active_membership.side_effect = get_active_membership

    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        message_processor=processor,
        routing_service=routing,
        request_manager=request_mgr,
    )

    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Does anyone have an axe?",
    )

    routing.fan_out.assert_not_called()
    assert result["processing"] == "auto_routing_skipped_no_recipients"
