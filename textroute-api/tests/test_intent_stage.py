"""Stage 1: delivery does not wait on intent, and each reply is recorded once."""

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.core.processors.message_processor import ProcessingResult
from src.core.providers.request_analyzer import RequestAnalysis
from src.domain.intent_status import IntentStatus
from src.domain.message_role import MessageKind
from src.domain.message_status import MessageWorkflowStatus
from src.services.inbound_message_service import InboundMessageService
from src.services.intent_service import IntentService
from tests.test_inbound_message_service import _request_manager, _service


def _analysis():
    return RequestAnalysis(
        request_type="request_borrow",
        summary="Borrow a saw",
        extracted_filters={},
        confidence=0.9,
        model_name="test",
    )


def test_discover_commits_analysis_and_ready_together_then_claims_once():
    request = SimpleNamespace(
        id=4,
        group_id=uuid4(),
        requester_id=uuid4(),
        original_message_id=uuid4(),
        intent_status=IntentStatus.PENDING.value,
    )
    original = SimpleNamespace(id=request.original_message_id, body="Need a saw", parent_message_id=None)
    deferred = SimpleNamespace(
        id=uuid4(),
        member_id=uuid4(),
        parent_message_id=original.id,
        processing_notes="reply_deferred",
        workflow_status="received",
    )

    db = MagicMock()
    request_mgr = MagicMock()
    request_mgr.find_by_id.return_value = request
    request_mgr.claim_intent_ready.return_value = True
    message_mgr = MagicMock()
    message_mgr.find_by_id.return_value = original
    message_mgr.claim_deferred_replies.return_value = [deferred]
    analyzer = MagicMock()
    analyzer.analyze.return_value = _analysis()
    processor = MagicMock()
    processor.process.return_value = ProcessingResult(intent="request_borrow", confidence=0.4)

    result = IntentService(
        request_manager=request_mgr,
        message_manager=message_mgr,
        request_analyzer=analyzer,
        message_processor=processor,
    ).discover(db, 4)

    assert result == "ready"
    assert request_mgr.apply_analysis.called
    assert request_mgr.claim_intent_ready.called
    assert message_mgr.claim_deferred_replies.called
    # Analysis and the ready flip are committed once, after both writes.
    assert db.commit.called
    assert message_mgr.set_workflow_status.call_args.kwargs["processing_notes"] == "reply_recorded_unprocessed"
    assert request_mgr.apply_analysis.call_args.kwargs["request_type"] == "request_borrow"
    apply_order = request_mgr.method_calls.index(next(c for c in request_mgr.method_calls if c[0] == "apply_analysis"))
    claim_order = request_mgr.method_calls.index(next(c for c in request_mgr.method_calls if c[0] == "claim_intent_ready"))
    assert apply_order < claim_order
    assert db.commit.call_count == 2


def test_losing_the_ready_claim_does_not_drain_replies():
    request = SimpleNamespace(
        id=4,
        requester_id=uuid4(),
        original_message_id=None,
        intent_status=IntentStatus.PENDING.value,
    )
    db = MagicMock()
    request_mgr = MagicMock()
    request_mgr.find_by_id.return_value = request
    request_mgr.claim_intent_ready.return_value = False
    message_mgr = MagicMock()
    analyzer = MagicMock()
    analyzer.analyze.return_value = _analysis()
    processor = MagicMock()
    processor.process.return_value = ProcessingResult(intent="general", confidence=0.2)

    result = IntentService(
        request_manager=request_mgr,
        message_manager=message_mgr,
        request_analyzer=analyzer,
        message_processor=processor,
    ).discover(db, 4)

    assert result == "skipped"
    db.rollback.assert_called()
    message_mgr.claim_deferred_replies.assert_not_called()
    db.commit.assert_not_called()


def test_analyzer_failure_marks_failed_and_does_not_claim_ready():
    request = SimpleNamespace(
        id=4,
        requester_id=uuid4(),
        original_message_id=None,
        intent_status=IntentStatus.PENDING.value,
    )
    db = MagicMock()
    request_mgr = MagicMock()
    request_mgr.find_by_id.return_value = request
    analyzer = MagicMock()
    analyzer.analyze.side_effect = RuntimeError("ollama down")
    processor = MagicMock()
    processor.process.return_value = ProcessingResult(intent="general", confidence=0.2)

    result = IntentService(
        request_manager=request_mgr,
        message_manager=MagicMock(),
        request_analyzer=analyzer,
        message_processor=processor,
    ).discover(db, 4)

    assert result == "failed"
    request_mgr.mark_intent_failed.assert_called_once_with(db, 4)
    request_mgr.claim_intent_ready.assert_not_called()
    db.commit.assert_called_once()


def test_a_second_discover_does_not_run_when_already_ready():
    request = SimpleNamespace(id=4, intent_status=IntentStatus.READY.value, request_type="announcement")
    db = MagicMock()
    request_mgr = MagicMock()
    request_mgr.find_by_id.return_value = request
    analyzer = MagicMock()

    result = IntentService(
        request_manager=request_mgr,
        message_manager=MagicMock(),
        request_analyzer=analyzer,
    ).discover(db, 4)

    assert result == "skipped"
    analyzer.analyze.assert_not_called()
    request_mgr.claim_intent_ready.assert_not_called()


def _reply_service(intent_status):
    db = MagicMock()
    group_id = uuid4()
    member_id = uuid4()
    parent_id = uuid4()
    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id, routing_policy="auto_group"),
    )
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=member_id, phone_number="+15551234567"
    )
    membership_mgr.get_active_membership.return_value = SimpleNamespace(id=uuid4())
    message = SimpleNamespace(
        id=uuid4(),
        parent_message_id=parent_id,
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.find_pending_clarification.return_value = None
    message_mgr.create_inbound.return_value = message
    open_request = SimpleNamespace(
        id=11,
        original_message_id=parent_id,
        intent_status=intent_status,
    )
    request_mgr = _request_manager()
    request_mgr.find_open_for_participant.return_value = [open_request]
    analyzer = MagicMock()
    routing = MagicMock()
    service = _service(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        request_manager=request_mgr,
        routing_service=routing,
    )
    service.request_analyzer = analyzer
    return db, service, message_mgr, routing, analyzer


def test_reply_while_pending_is_deferred_and_not_fanned_out():
    db, service, message_mgr, routing, analyzer = _reply_service(IntentStatus.PENDING.value)
    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="I have one",
    )
    assert result["processing"] == "reply_deferred"
    routing.fan_out.assert_not_called()
    analyzer.analyze.assert_not_called()
    assert message_mgr.set_workflow_status.call_args.kwargs["processing_notes"] == "reply_deferred"


def test_reply_after_ready_is_recorded_once_and_not_fanned_out():
    db, service, message_mgr, routing, _ = _reply_service(IntentStatus.READY.value)
    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="I have one",
    )
    assert result["processing"] == "reply_recorded"
    assert result["kind"] == MessageKind.MEMBER_REPLY.value
    routing.fan_out.assert_not_called()
    notes = [
        call.kwargs.get("processing_notes")
        for call in message_mgr.set_workflow_status.call_args_list
    ]
    assert notes.count("reply_recorded_unprocessed") == 1
    assert "reply_deferred" not in notes


def test_new_request_does_not_call_the_analyzer_on_the_webhook():
    db = MagicMock()
    group_id = uuid4()
    member_id = uuid4()
    phone_mgr = MagicMock()
    phone_mgr.find_by_number.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15559876543",
        group_id=group_id,
        status="assigned",
        group=SimpleNamespace(id=group_id, routing_policy="auto_group"),
    )
    membership_mgr = MagicMock()
    membership_mgr.get_by_phone.return_value = SimpleNamespace(
        id=member_id, phone_number="+15551234567"
    )
    other = SimpleNamespace(id=uuid4(), phone_number="+15550001111", name="B")
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        id=uuid4(), member=other
    )
    membership_mgr.list_active_memberships.return_value = [
        SimpleNamespace(member=other, role="member"),
    ]
    message = SimpleNamespace(
        id=uuid4(),
        body="Can anyone help me move Saturday?",
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
        parent_message_id=None,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.find_pending_clarification.return_value = None
    message_mgr.create_inbound.return_value = message
    request_mgr = _request_manager()
    routing = MagicMock()
    routing.fan_out.return_value = {"delivered_outbound_ids": ["1"], "delivery_failures": []}
    analyzer = MagicMock()
    service = InboundMessageService(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        request_manager=request_mgr,
        routing_service=routing,
        request_analyzer=analyzer,
        request_event_manager=MagicMock(),
    )
    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Can anyone help me move Saturday?",
    )
    analyzer.analyze.assert_not_called()
    request_mgr.apply_analysis.assert_not_called()
    routing.fan_out.assert_called_once()
    assert result["discover_intent"] is True
    assert result["routing_policy"] == "auto_group"


def test_moderator_required_does_not_fan_out_but_still_discovers_intent():
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
    membership_mgr.list_active_memberships.return_value = []
    message = SimpleNamespace(
        id=uuid4(),
        body="Can anyone help me move Saturday?",
        workflow_status=MessageWorkflowStatus.RECEIVED.value,
        parent_message_id=None,
    )
    message_mgr = MagicMock()
    message_mgr.find_by_provider_message_id.return_value = None
    message_mgr.find_pending_clarification.return_value = None
    message_mgr.create_inbound.return_value = message
    routing = MagicMock()
    analyzer = MagicMock()
    service = InboundMessageService(
        phone_number_manager=phone_mgr,
        membership_manager=membership_mgr,
        message_manager=message_mgr,
        request_manager=_request_manager(),
        routing_service=routing,
        request_analyzer=analyzer,
        request_event_manager=MagicMock(),
    )
    result = service.handle_incoming_message(
        db,
        from_phone_number="+15551234567",
        to_phone_number="+15559876543",
        body="Can anyone help me move Saturday?",
    )
    routing.fan_out.assert_not_called()
    analyzer.analyze.assert_not_called()
    assert result["discover_intent"] is True
    assert result["routing_policy"] == "moderator_required"
