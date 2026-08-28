from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.dependencies import get_moderator_context
from src.api.routes.moderator import moderation as moderation_route
from src.config.config import Config
from src.db.db import get_db
from src.main import app
from src.services.auth_service import ModeratorContext


def _context(group_id):
    return ModeratorContext(
        session_id=uuid4(),
        group_id=group_id,
        moderator_member_id=uuid4(),
        group_name="Neighbors",
        group_phone_number="+15550001001",
        expires_at=datetime.now(timezone.utc),
    )


def test_queue_uses_authenticated_group(monkeypatch):
    group_id = uuid4()
    context = _context(group_id)
    list_queue = MagicMock(return_value=[])
    monkeypatch.setattr(
        moderation_route.ModerationService,
        "list_queue",
        list_queue,
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_moderator_context] = lambda: context

    try:
        response = TestClient(app).get("/moderation/queue")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert list_queue.call_args.args[1] == group_id


def test_list_messages_uses_authenticated_group(monkeypatch):
    group_id = uuid4()
    list_messages = MagicMock(return_value=[])
    monkeypatch.setattr(
        moderation_route.ModerationService,
        "list_messages",
        list_messages,
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_moderator_context] = lambda: _context(group_id)

    try:
        response = TestClient(app).get("/messages")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    # The group is never taken from the client.
    assert list_messages.call_args.args[1] == group_id


def test_list_messages_does_not_collide_with_message_detail(monkeypatch):
    """The static /messages path must not be swallowed by /messages/{id}."""
    group_id = uuid4()
    list_messages = MagicMock(return_value=[])
    get_message = MagicMock(return_value={})
    monkeypatch.setattr(
        moderation_route.ModerationService, "list_messages", list_messages
    )
    monkeypatch.setattr(
        moderation_route.ModerationService, "get_message", get_message
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_moderator_context] = lambda: _context(group_id)

    try:
        TestClient(app).get("/messages")
    finally:
        app.dependency_overrides.clear()

    list_messages.assert_called_once()
    get_message.assert_not_called()


def test_messages_endpoint_requires_moderator_session():
    original_secret = Config.AUTH_SECRET
    Config.AUTH_SECRET = "test-secret-at-least-thirty-two-characters"
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        response = TestClient(app).get("/messages")
    finally:
        app.dependency_overrides.clear()
        Config.AUTH_SECRET = original_secret

    assert response.status_code == 401
