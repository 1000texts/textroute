"""Per-request rollups: who is a participant, and what the list pane reads.

The SQL itself is exercised end-to-end against Postgres; these tests pin the
rules that are easy to break silently -- which kinds make someone a party to a
request, the order the rollup columns are unpacked in, and the promise that a
page of requests costs one rollup query rather than one per row.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.core.managers.request_manager import RequestManager
from src.domain.message_role import PARTICIPANT_KINDS, MessageKind
from src.services.request_service import RequestService

GROUP_ID = uuid4()


def _request(**overrides):
    base = dict(
        id=7,
        group_id=GROUP_ID,
        requester_id=uuid4(),
        status="open",
        request_type="request_borrow",
        summary="borrow: axe",
        confidence=None,
        extracted_filters={},
        embedding=None,
        model_name=None,
        original_message_id=uuid4(),
        created_at=datetime.now(timezone.utc),
        completed_at=None,
        cancelled_at=None,
        expires_at=None,
        last_activity_at=datetime.now(timezone.utc),
        group=SimpleNamespace(id=GROUP_ID),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _service(**kwargs):
    membership_mgr = MagicMock()
    membership_mgr.get_membership.return_value = None
    return RequestService(
        request_manager=kwargs.pop("request_manager", None) or MagicMock(),
        request_event_manager=MagicMock(),
        message_manager=MagicMock(),
        membership_manager=membership_mgr,
        phone_number_manager=MagicMock(),
        messaging_service=MagicMock(),
        routing_service=MagicMock(),
    )


# -- who counts as a participant -------------------------------------------


def test_a_moderator_is_an_actor_not_a_participant():
    """The moderator acts on a request without being a party to it.

    Their clarification names its *recipient* in member_id, so counting by kind
    is what keeps them out; counting every member_id in the thread would not.
    """
    assert MessageKind.MODERATOR_CLARIFICATION not in PARTICIPANT_KINDS


def test_the_member_side_of_a_request_all_counts():
    assert PARTICIPANT_KINDS == {
        MessageKind.ORIGINAL_REQUEST,
        MessageKind.FANOUT_COPY,
        MessageKind.MEMBER_REPLY,
        MessageKind.CONFIRMATION,
    }


# -- the rollup query ------------------------------------------------------


def test_rollup_maps_each_column_to_the_right_field():
    """Four positional columns, so a reordering would silently swap meanings."""
    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
        (7, 4, 3, True),
        (8, 1, 1, False),
    ]

    rollups = RequestManager().summarize_activity(db, request_ids=[7, 8])

    assert rollups[7] == {
        "message_count": 4,
        "participant_count": 3,
        "needs_review": True,
    }
    assert rollups[8]["needs_review"] is False


def test_rollup_does_not_compute_last_activity():
    """It belongs to the requests table, because the sweep filters on it.

    Two answers to "when did this last see activity" is one too many: the one
    shown to a moderator would be free to drift from the one that closes the
    request.
    """
    db = MagicMock()
    db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
        (7, 4, 3, True),
    ]

    rollups = RequestManager().summarize_activity(db, request_ids=[7])

    assert "last_activity_at" not in rollups[7]


def test_rollup_skips_the_query_when_there_is_nothing_to_roll_up():
    db = MagicMock()

    assert RequestManager().summarize_activity(db, request_ids=[]) == {}
    db.query.assert_not_called()


# -- what the list pane reads ----------------------------------------------


def test_a_page_of_requests_costs_one_rollup_query():
    db = MagicMock()
    requests = [_request(id=1), _request(id=2), _request(id=3)]
    request_mgr = MagicMock()
    request_mgr.list_for_group.return_value = requests
    request_mgr.summarize_activity.return_value = {}
    service = _service(request_manager=request_mgr)

    service.list_requests(db, GROUP_ID)

    request_mgr.summarize_activity.assert_called_once_with(db, request_ids=[1, 2, 3])


def test_summary_reports_the_rollup_for_its_own_request():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    last_activity = datetime.now(timezone.utc)
    request_mgr = MagicMock()
    request_mgr.list_for_group.return_value = [
        _request(id=7, last_activity_at=last_activity)
    ]
    request_mgr.summarize_activity.return_value = {
        7: {
            "message_count": 5,
            "participant_count": 3,
            "needs_review": True,
        }
    }
    service = _service(request_manager=request_mgr)

    (summary,) = service.list_requests(db, GROUP_ID)

    assert summary["participant_count"] == 3
    assert summary["message_count"] == 5
    assert summary["needs_review"] is True
    # From the request row, not the rollup: the same value the sweep judges.
    assert summary["last_activity_at"] == last_activity.isoformat()


def test_a_request_with_no_messages_reports_zeroes_not_nulls():
    """The list renders these directly, so absent must mean 0, not undefined."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request_mgr = MagicMock()
    request_mgr.list_for_group.return_value = [_request(id=7)]
    request_mgr.summarize_activity.return_value = {}
    service = _service(request_manager=request_mgr)

    (summary,) = service.list_requests(db, GROUP_ID)

    assert summary["participant_count"] == 0
    assert summary["message_count"] == 0
    assert summary["needs_review"] is False
    # Still a real timestamp: a request is active from the moment it exists, so
    # this is NOT NULL even before any message lands.
    assert summary["last_activity_at"] is not None


# -- analyzer confidence ---------------------------------------------------


def test_analysis_confidence_is_stored_on_the_request():
    """It describes the request, so it must not be read off a message."""
    db = MagicMock()
    request = _request()

    RequestManager().apply_analysis(
        db,
        request,
        request_type="request_borrow",
        extracted_filters={"object": "axe"},
        summary="borrow: axe",
        embedding=None,
        model_name="qwen2",
        confidence=0.91,
    )

    assert request.confidence == 0.91


def test_an_unanalyzed_request_reports_no_confidence():
    """Null is not zero: never analyzed and genuinely unsure differ."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request_mgr = MagicMock()
    request_mgr.list_for_group.return_value = [_request(confidence=None)]
    request_mgr.summarize_activity.return_value = {}
    service = _service(request_manager=request_mgr)

    (summary,) = service.list_requests(db, GROUP_ID)

    assert summary["confidence"] is None


def test_confidence_survives_serialization_as_a_float():
    """Numeric columns can arrive as Decimal, which JSON will not take."""
    from decimal import Decimal

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    request_mgr = MagicMock()
    request_mgr.list_for_group.return_value = [_request(confidence=Decimal("0.91"))]
    request_mgr.summarize_activity.return_value = {}
    service = _service(request_manager=request_mgr)

    (summary,) = service.list_requests(db, GROUP_ID)

    assert isinstance(summary["confidence"], float)
    assert summary["confidence"] == 0.91
