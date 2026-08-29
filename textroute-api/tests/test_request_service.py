"""Request lifecycle: resolution, expiry, and moderator-authored messages."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.providers.sms_provider import SmsProviderError
from src.domain.message_role import MessageKind, RequestEventType
from src.services.request_service import (
    NoRecipientsError,
    RequestError,
    RequestNotFoundError,
    RequestNotOpenError,
    RequestService,
)

GROUP_ID = uuid4()


def _request(**overrides):
    base = dict(
        id=7,
        group_id=GROUP_ID,
        requester_id=uuid4(),
        status="open",
        request_type="request_borrow",
        summary="borrow: axe",
        confidence=0.91,
        extracted_filters={"object": "axe"},
        embedding=None,
        model_name=None,
        original_message_id=uuid4(),
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        cancelled_at=None,
        expires_at=None,
        group=SimpleNamespace(id=GROUP_ID),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _service(request, **kwargs):
    request_mgr = kwargs.pop("request_manager", None) or MagicMock()
    request_mgr.find_for_group.return_value = request
    # A real dict, so _summary reads real defaults rather than MagicMocks.
    request_mgr.summarize_activity.return_value = {}
    membership_mgr = kwargs.pop("membership_manager", None) or MagicMock()
    membership_mgr.get_membership.return_value = None
    service = RequestService(
        request_manager=request_mgr,
        request_event_manager=kwargs.pop("request_event_manager", None)
        or MagicMock(),
        message_manager=MagicMock(),
        membership_manager=membership_mgr,
        phone_number_manager=MagicMock(),
        messaging_service=kwargs.pop("messaging_service", None) or MagicMock(),
        routing_service=kwargs.pop("routing_service", None) or MagicMock(),
    )
    return service


# -- resolution -------------------------------------------------------------


@pytest.mark.parametrize(
    "action, event_type",
    [
        ("complete", RequestEventType.COMPLETED),
        ("cancel", RequestEventType.CANCELLED),
    ],
)
def test_resolving_a_request_records_its_transition(action, event_type):
    db = MagicMock()
    request = _request()
    event_mgr = MagicMock()
    service = _service(request, request_event_manager=event_mgr)

    getattr(service, action)(db, 7, group_id=GROUP_ID)

    getattr(service.request_manager, action).assert_called_once()
    assert event_mgr.record.call_args.kwargs["event_type"] is event_type
    db.commit.assert_called_once()


def test_a_closed_request_cannot_be_resolved_again():
    db = MagicMock()
    service = _service(_request(status="completed"))

    with pytest.raises(RequestNotOpenError):
        service.complete(db, 7, group_id=GROUP_ID)


def test_another_groups_request_looks_like_not_found():
    """No existence leak across groups: the scoped lookup simply misses."""
    db = MagicMock()
    service = _service(None)

    with pytest.raises(RequestNotFoundError):
        service.get_request(db, 7, group_id=GROUP_ID)


def test_sweep_closes_open_requests_past_expiry():
    """Without this an abandoned request keeps capturing unrelated messages."""
    db = MagicMock()
    expired_at = datetime.now(timezone.utc) - timedelta(hours=1)
    stale = [_request(id=1, expires_at=expired_at), _request(id=2, expires_at=expired_at)]

    request_mgr = MagicMock()
    request_mgr.list_open_past_expiry.return_value = stale
    event_mgr = MagicMock()
    service = _service(
        None, request_manager=request_mgr, request_event_manager=event_mgr
    )

    assert service.sweep_expired(db) == 2
    assert request_mgr.expire.call_count == 2
    assert [c.kwargs["event_type"] for c in event_mgr.record.call_args_list] == [
        RequestEventType.EXPIRED,
        RequestEventType.EXPIRED,
    ]


# -- moderator-authored messages -------------------------------------------


def test_moderator_message_is_attributed_to_its_author():
    """The row must say a person wrote this, unlike a fan-out copy."""
    db = MagicMock()
    requester_id = uuid4()
    moderator_id = uuid4()
    request = _request(requester_id=requester_id)

    requester = SimpleNamespace(id=requester_id, phone_number="+15551112222")
    membership_mgr = MagicMock()
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        member=requester
    )
    membership_mgr.get_membership.return_value = None

    messaging = MagicMock()
    messaging.send_message.return_value = SimpleNamespace(id=uuid4())
    routing = MagicMock()
    routing.resolve_from_number.return_value = "+15559876543"

    service = _service(
        request,
        membership_manager=membership_mgr,
        messaging_service=messaging,
        routing_service=routing,
    )

    result = service.send_moderator_message(
        db,
        7,
        group_id=GROUP_ID,
        author_member_id=moderator_id,
        body="  Which day works for you?  ",
    )

    assert len(result["sent_message_ids"]) == 1
    sent = messaging.send_message.call_args.kwargs
    assert sent["kind"] is MessageKind.MODERATOR_CLARIFICATION
    assert sent["author_member_id"] == moderator_id
    # Author and subject differ here, which is exactly what distinguishes a
    # clarification from a member's own message.
    assert sent["to_member"] is requester
    assert sent["request_id"] == 7
    assert sent["body"] == "Which day works for you?"


def test_moderator_message_defaults_to_the_requester_alone():
    """A clarifying question should not broadcast to everyone who was routed to."""
    db = MagicMock()
    requester_id = uuid4()
    request = _request(requester_id=requester_id)

    membership_mgr = MagicMock()
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        member=SimpleNamespace(id=requester_id, phone_number="+15551112222")
    )
    membership_mgr.get_membership.return_value = None

    messaging = MagicMock()
    messaging.send_message.return_value = SimpleNamespace(id=uuid4())
    routing = MagicMock()
    routing.resolve_from_number.return_value = "+15559876543"

    service = _service(
        request,
        membership_manager=membership_mgr,
        messaging_service=messaging,
        routing_service=routing,
    )
    service.send_moderator_message(
        db, 7, group_id=GROUP_ID, author_member_id=uuid4(), body="hi"
    )

    assert membership_mgr.get_active_membership.call_args.kwargs["member_id"] == (
        requester_id
    )


def test_moderator_message_requires_a_body():
    db = MagicMock()
    service = _service(_request())

    with pytest.raises(RequestError):
        service.send_moderator_message(
            db, 7, group_id=GROUP_ID, author_member_id=uuid4(), body="   "
        )


def test_moderator_message_needs_an_active_recipient():
    db = MagicMock()
    membership_mgr = MagicMock()
    membership_mgr.get_active_membership.return_value = None
    membership_mgr.get_membership.return_value = None
    service = _service(_request(), membership_manager=membership_mgr)

    with pytest.raises(NoRecipientsError):
        service.send_moderator_message(
            db, 7, group_id=GROUP_ID, author_member_id=uuid4(), body="hi"
        )


def test_moderator_message_provider_failure_is_reported_not_raised():
    """One unreachable member must not lose the whole action."""
    db = MagicMock()
    requester_id = uuid4()
    membership_mgr = MagicMock()
    membership_mgr.get_active_membership.return_value = SimpleNamespace(
        member=SimpleNamespace(id=requester_id, phone_number="+15551112222")
    )
    membership_mgr.get_membership.return_value = None

    messaging = MagicMock()
    messaging.send_message.side_effect = SmsProviderError("carrier down")
    routing = MagicMock()
    routing.resolve_from_number.return_value = "+15559876543"

    service = _service(
        _request(requester_id=requester_id),
        membership_manager=membership_mgr,
        messaging_service=messaging,
        routing_service=routing,
    )
    result = service.send_moderator_message(
        db, 7, group_id=GROUP_ID, author_member_id=uuid4(), body="hi"
    )

    assert result["sent_message_ids"] == []
    assert result["failures"][0]["error"] == "carrier down"


def test_a_closed_request_cannot_be_spoken_into():
    db = MagicMock()
    service = _service(_request(status="expired"))

    with pytest.raises(RequestNotOpenError):
        service.send_moderator_message(
            db, 7, group_id=GROUP_ID, author_member_id=uuid4(), body="hi"
        )


# -- serialization ----------------------------------------------------------


def test_request_detail_never_serializes_the_embedding():
    """A thousand floats are of no use to a browser; presence is."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request = _request(embedding=[0.1] * 1024)

    request_mgr = MagicMock()
    request_mgr.find_for_group.return_value = request
    request_mgr.load_thread.return_value = []
    service = _service(request, request_manager=request_mgr)

    detail = service.get_request(db, 7, group_id=GROUP_ID)

    assert detail["has_embedding"] is True
    assert "embedding" not in detail
