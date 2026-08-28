"""The inbound webhook is public, so it must not accept unauthenticated posts.

Without this guard anyone who learns the API URL can forge an inbound SMS into
a real group, and under the auto_group routing policy that fans out real
messages to real people.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.routes.webhooks import inbound as inbound_route
from src.config.config import Config
from src.db.db import get_db
from src.main import app

SECRET = "test-webhook-secret"

PAYLOAD = {
    "from": "+15551110000",
    "to": "+15550001001",
    "body": "Does anyone have an axe?",
}


@pytest.fixture
def secret_configured():
    original = Config.WEBHOOK_SECRET
    Config.WEBHOOK_SECRET = SECRET
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        Config.WEBHOOK_SECRET = original


@pytest.mark.parametrize("path", ["/webhook/messages", "/webhook/inbound"])
def test_missing_secret_is_rejected(secret_configured, path):
    response = TestClient(app).post(path, json=PAYLOAD)

    assert response.status_code == 401


def test_wrong_secret_is_rejected(secret_configured):
    response = TestClient(app).post(
        "/webhook/messages",
        json=PAYLOAD,
        headers={"X-Webhook-Secret": "not-the-secret"},
    )

    assert response.status_code == 401


def test_rejection_happens_before_any_message_handling(secret_configured, monkeypatch):
    """An unauthenticated post must not reach the database or the service."""
    handle = MagicMock()
    monkeypatch.setattr(
        inbound_route.InboundMessageService,
        "handle_incoming_message",
        handle,
    )

    TestClient(app).post("/webhook/messages", json=PAYLOAD)

    handle.assert_not_called()


def test_correct_secret_is_accepted(secret_configured, monkeypatch):
    monkeypatch.setattr(
        inbound_route.InboundMessageService,
        "handle_incoming_message",
        MagicMock(return_value={"status": "received"}),
    )

    response = TestClient(app).post(
        "/webhook/messages",
        json=PAYLOAD,
        headers={"X-Webhook-Secret": SECRET},
    )

    assert response.status_code == 200


def test_unset_secret_fails_closed(monkeypatch):
    """A misconfigured deployment must be unreachable, never open."""
    original = Config.WEBHOOK_SECRET
    Config.WEBHOOK_SECRET = None
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        response = TestClient(app).post("/webhook/messages", json=PAYLOAD)
    finally:
        app.dependency_overrides.clear()
        Config.WEBHOOK_SECRET = original

    assert response.status_code == 503
