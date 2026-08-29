"""Routing policy read/write, scoped to the authenticated moderator's group."""

from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.dependencies import get_moderator_context
from src.api.routes.moderator import group_settings as group_route
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
        expires_at=MagicMock(),
    )


def test_group_settings_requires_moderator_session():
    original_secret = Config.AUTH_SECRET
    Config.AUTH_SECRET = "test-secret-at-least-thirty-two-characters"
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        response = TestClient(app).get("/group/settings")
    finally:
        app.dependency_overrides.clear()
        Config.AUTH_SECRET = original_secret

    assert response.status_code == 401


def test_update_routing_policy_uses_group_from_session(monkeypatch):
    group_id = uuid4()
    set_policy = MagicMock(
        return_value={
            "id": str(group_id),
            "name": "Neighbors",
            "description": None,
            "status": "active",
            "routing_policy": "auto_group",
        }
    )
    monkeypatch.setattr(
        group_route.GroupService, "set_routing_policy", set_policy
    )
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_moderator_context] = lambda: _context(group_id)
    try:
        response = TestClient(app).patch(
            "/group/settings",
            json={"routing_policy": "auto_group"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["routing_policy"] == "auto_group"
    # The group is never taken from the request body.
    assert set_policy.call_args.args[1] == group_id
    assert set_policy.call_args.kwargs["routing_policy"] == "auto_group"


def test_reserved_auto_matched_policy_is_rejected():
    """Reserved in the schema, not yet honored by the router — say so loudly."""
    group_id = uuid4()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_moderator_context] = lambda: _context(group_id)
    try:
        response = TestClient(app).patch(
            "/group/settings",
            json={"routing_policy": "auto_matched"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "not implemented" in response.json()["detail"]


def test_unknown_policy_is_rejected():
    group_id = uuid4()
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_moderator_context] = lambda: _context(group_id)
    try:
        response = TestClient(app).patch(
            "/group/settings",
            json={"routing_policy": "send_to_everyone_always"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
