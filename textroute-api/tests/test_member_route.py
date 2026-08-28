from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.dependencies import get_moderator_context
from src.api.routes.moderator import members as member_route
from src.config.config import Config
from src.db.db import get_db
from src.main import app
from src.services.auth_service import ModeratorContext
from src.services.member_service import AddedMember


def test_members_endpoint_requires_moderator_session():
    original_secret = Config.AUTH_SECRET
    Config.AUTH_SECRET = "test-secret-at-least-thirty-two-characters"
    app.dependency_overrides[get_db] = lambda: MagicMock()
    try:
        response = TestClient(app).post(
            "/members",
            json={
                "members": [
                    {"phone_number": "+15551234567", "name": "Alice"}
                ],
                "consent_confirmed": True,
            },
        )
    finally:
        app.dependency_overrides.clear()
        Config.AUTH_SECRET = original_secret

    assert response.status_code == 401


def test_members_endpoint_uses_group_from_authenticated_session(monkeypatch):
    group_id = uuid4()
    context = ModeratorContext(
        session_id=uuid4(),
        group_id=group_id,
        moderator_member_id=uuid4(),
        group_name="Neighbors",
        group_phone_number="+15550001001",
        expires_at=MagicMock(),
    )
    db = MagicMock()
    member = AddedMember(
        member_id=uuid4(),
        membership_id=uuid4(),
        phone_number="+15551234567",
        name="Alice",
    )
    add_members = MagicMock(return_value=[member])
    monkeypatch.setattr(member_route.MemberService, "add_members", add_members)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_moderator_context] = lambda: context

    try:
        response = TestClient(app).post(
            "/members",
            json={
                "members": [
                    {"phone_number": "+1 555 123 4567", "name": "Alice"}
                ],
                "consent_confirmed": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["group_id"] == str(group_id)
    assert add_members.call_args.kwargs["group_id"] == group_id


def test_members_endpoint_rolls_back_failed_batch(monkeypatch):
    context = ModeratorContext(
        session_id=uuid4(),
        group_id=uuid4(),
        moderator_member_id=uuid4(),
        group_name="Neighbors",
        group_phone_number="+15550001001",
        expires_at=MagicMock(),
    )
    db = MagicMock()
    monkeypatch.setattr(
        member_route.MemberService,
        "add_members",
        MagicMock(side_effect=RuntimeError("write failed")),
    )
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_moderator_context] = lambda: context

    try:
        response = TestClient(app).post(
            "/members",
            json={
                "members": [
                    {"phone_number": "+15551234567", "name": "Alice"}
                ],
                "consent_confirmed": True,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    db.rollback.assert_called_once()
