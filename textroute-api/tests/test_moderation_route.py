from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from src.api.dependencies import get_moderator_context
from src.api.routes import moderation as moderation_route
from src.db.db import get_db
from src.main import app
from src.services.auth_service import ModeratorContext


def test_queue_uses_authenticated_group(monkeypatch):
    group_id = uuid4()
    context = ModeratorContext(
        session_id=uuid4(),
        group_id=group_id,
        moderator_member_id=uuid4(),
        group_name="Neighbors",
        group_phone_number="+15550001001",
        expires_at=datetime.now(timezone.utc),
    )
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
