"""The conversation read the SMS simulator uses for its history.

Guarded by the webhook secret rather than a moderator session, because the
simulator holds only that secret and production nginx injects it for
``/api/webhook/`` and nothing else.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.routes.webhooks import conversation as conversation_route
from src.config.config import Config
from src.core.phone_normalize import InvalidPhoneNumberError
from src.db.db import get_db
from src.main import app
from src.services.inbound_errors import (
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
)

SECRET = "test-webhook-secret"
NUMBERS = {"from": "+15551112222", "to": "+15559876543"}


def _row(**overrides):
    """One message row as the service hands it over."""
    row = {
        "id": uuid4(),
        "direction": "inbound",
        "body": "Does anyone have an axe?",
        "kind": "original_request",
        "workflow_status": "received",
        "created_at": datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def _call(monkeypatch, *, returns=None, raises=None, params=None, secret=SECRET):
    """Drive the route with the service stubbed out."""
    load = MagicMock(side_effect=raises, return_value=returns or [])
    monkeypatch.setattr(conversation_route.SimulatorService, "load_conversation", load)
    monkeypatch.setattr(Config, "WEBHOOK_SECRET", SECRET)
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        response = TestClient(app).get(
            "/webhook/conversation",
            params={**NUMBERS, **(params or {})},
            headers={"X-Webhook-Secret": secret} if secret else {},
        )
    finally:
        app.dependency_overrides.clear()
    return response, load


def test_conversation_requires_the_webhook_secret(monkeypatch):
    response, load = _call(monkeypatch, secret=None)

    assert response.status_code == 401
    load.assert_not_called()


def test_conversation_returns_both_directions(monkeypatch):
    sent = _row(direction="inbound", body="Does anyone have an axe?")
    received = _row(
        direction="outbound",
        kind="fanout_copy",
        workflow_status="sent",
        body="Does anyone have an axe?",
    )

    response, _ = _call(monkeypatch, returns=[sent, received])

    assert response.status_code == 200
    payload = response.json()
    assert [m["direction"] for m in payload["messages"]] == ["inbound", "outbound"]
    # The handset shows what reached it, whatever the message's role: deciding
    # which of them mattered is the request's job, not the phone's.
    assert payload["messages"][1]["kind"] == "fanout_copy"
    assert payload["server_time"]


def test_the_body_is_served_verbatim(monkeypatch):
    """Including the sender prefix, which is part of the SMS that was sent rather
    than something this endpoint or the client composes. Nothing here decorates
    text: the handset has to be able to show what a real one would."""
    response, _ = _call(
        monkeypatch,
        returns=[
            _row(
                direction="outbound",
                kind="moderator_clarification",
                workflow_status="sent",
                body="Austin (Moderator): Could you clarify your question?",
            )
        ],
    )

    message = response.json()["messages"][0]
    assert message["body"] == "Austin (Moderator): Could you clarify your question?"
    # No parallel sender field: one label beside another in the text is how the
    # two get to disagree.
    assert "sender_name" not in message


def test_a_number_nobody_has_texted_is_an_empty_conversation(monkeypatch):
    """Not an error. Typing a new From number should show an empty thread."""
    response, _ = _call(monkeypatch, returns=[])

    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_unknown_group_number_is_not_found(monkeypatch):
    response, _ = _call(
        monkeypatch,
        raises=UnknownReceivingNumberError("Unknown TextRoute number"),
    )

    assert response.status_code == 404


def test_group_number_without_a_group_is_not_found(monkeypatch):
    response, _ = _call(
        monkeypatch,
        raises=UnassignedPhoneNumberError("Not assigned to a group"),
    )

    assert response.status_code == 404


def test_unparseable_number_is_rejected(monkeypatch):
    response, _ = _call(
        monkeypatch,
        raises=InvalidPhoneNumberError("nonsense is not a phone number"),
    )

    assert response.status_code == 400


def test_the_cursor_is_passed_through_as_a_pair(monkeypatch):
    after_id = uuid4()
    response, load = _call(
        monkeypatch,
        params={
            "after_created_at": "2026-08-29T12:00:00Z",
            "after_id": str(after_id),
        },
    )

    assert response.status_code == 200
    assert load.call_args.kwargs["after_id"] == after_id
    assert load.call_args.kwargs["after_created_at"] == datetime(
        2026, 8, 29, 12, 0, tzinfo=timezone.utc
    )


def test_half_a_cursor_is_rejected(monkeypatch):
    """Silently ignoring it would return a full reload dressed as a page of new
    messages, which the client would then append to what it already had."""
    response, load = _call(
        monkeypatch, params={"after_created_at": "2026-08-29T12:00:00Z"}
    )

    assert response.status_code == 400
    load.assert_not_called()

    response, load = _call(monkeypatch, params={"after_id": str(uuid4())})

    assert response.status_code == 400
    load.assert_not_called()
