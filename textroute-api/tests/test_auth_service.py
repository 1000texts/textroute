from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.core.providers.sms_provider import SmsProviderError
from src.services.auth_errors import (
    InvalidLoginChallengeError,
    InvalidModeratorCredentialsError,
    InvalidSessionError,
)
from src.services.auth_service import (
    AuthSettings,
    ModeratorAuthService,
    ModeratorContext,
)


def _service(*, expose_code: bool = True):
    return ModeratorAuthService(
        settings=AuthSettings(
            secret="test-secret-at-least-thirty-two-characters",
            challenge_ttl_seconds=600,
            session_ttl_seconds=3600,
            max_attempts=5,
            expose_development_code=expose_code,
        ),
        auth_manager=MagicMock(),
        membership_manager=MagicMock(),
        phone_number_manager=MagicMock(),
        sms_provider=MagicMock(),
    )


def test_request_challenge_for_active_moderator():
    db = MagicMock()
    service = _service()
    group_id = uuid4()
    moderator_id = uuid4()
    service.phone_number_manager.find_by_number.return_value = SimpleNamespace(
        group_id=group_id,
        status="assigned",
        phone_number="+15550001001",
    )
    service.membership_manager.get_by_phone.return_value = SimpleNamespace(
        id=moderator_id,
        phone_number="+15551234567",
    )
    service.membership_manager.get_active_membership.return_value = SimpleNamespace(
        role="moderator"
    )

    result = service.request_challenge(
        db,
        group_phone_number="+15550001001",
        moderator_phone_number="+15551234567",
    )

    assert result.development_code is not None
    assert len(result.development_code) == 6
    assert result.development_code.isdigit()
    call = service.auth_manager.create_challenge.call_args.kwargs
    assert call["code_hash"] != result.development_code
    assert len(call["code_hash"]) == 64
    send = service.sms_provider.send_sms.call_args.kwargs
    assert send["from_number"] == "+15550001001"
    assert send["to_number"] == "+15551234567"
    assert result.development_code in send["body"]
    db.commit.assert_called_once()


def test_challenge_delivery_failure_does_not_commit():
    db = MagicMock()
    service = _service()
    service.phone_number_manager.find_by_number.return_value = SimpleNamespace(
        group_id=uuid4(),
        status="assigned",
        phone_number="+15550001001",
    )
    service.membership_manager.get_by_phone.return_value = SimpleNamespace(
        id=uuid4(),
        phone_number="+15551234567",
    )
    service.membership_manager.get_active_membership.return_value = SimpleNamespace(
        role="moderator"
    )
    service.sms_provider.send_sms.side_effect = RuntimeError("provider down")

    with pytest.raises(SmsProviderError):
        service.request_challenge(
            db,
            group_phone_number="+15550001001",
            moderator_phone_number="+15551234567",
        )

    db.commit.assert_not_called()


def test_request_challenge_rejects_non_moderator():
    db = MagicMock()
    service = _service()
    service.phone_number_manager.find_by_number.return_value = SimpleNamespace(
        group_id=uuid4(),
        status="assigned",
    )
    service.membership_manager.get_by_phone.return_value = SimpleNamespace(id=uuid4())
    service.membership_manager.get_active_membership.return_value = SimpleNamespace(
        role="member"
    )

    with pytest.raises(InvalidModeratorCredentialsError):
        service.request_challenge(
            db,
            group_phone_number="+15550001001",
            moderator_phone_number="+15551234567",
        )

    service.auth_manager.create_challenge.assert_not_called()
    db.commit.assert_not_called()


def test_verify_challenge_creates_timed_session():
    db = MagicMock()
    service = _service()
    challenge_id = uuid4()
    group_id = uuid4()
    moderator_id = uuid4()
    code = "123456"
    challenge = SimpleNamespace(
        id=challenge_id,
        group_id=group_id,
        moderator_member_id=moderator_id,
        code_hash=service._hash_code(challenge_id, code),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        attempt_count=0,
        consumed_at=None,
    )
    service.auth_manager.get_challenge_for_update.return_value = challenge
    session = SimpleNamespace(
        id=uuid4(),
        group_id=group_id,
        moderator_member_id=moderator_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    service.auth_manager.create_session.return_value = session
    expected_context = ModeratorContext(
        session_id=session.id,
        group_id=group_id,
        moderator_member_id=moderator_id,
        group_name="Neighbors",
        group_phone_number="+15550001001",
        expires_at=session.expires_at,
    )
    service._build_context = MagicMock(return_value=expected_context)

    result = service.verify_challenge(
        db,
        challenge_id=challenge_id,
        code=code,
    )

    assert challenge.consumed_at is not None
    assert result.context == expected_context
    assert result.token
    token_hash = service.auth_manager.create_session.call_args.kwargs["token_hash"]
    assert result.token not in token_hash
    db.commit.assert_called_once()


def test_wrong_code_increments_attempt_count():
    db = MagicMock()
    service = _service()
    challenge_id = uuid4()
    challenge = SimpleNamespace(
        id=challenge_id,
        code_hash=service._hash_code(challenge_id, "123456"),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        attempt_count=0,
        consumed_at=None,
    )
    service.auth_manager.get_challenge_for_update.return_value = challenge

    with pytest.raises(InvalidLoginChallengeError):
        service.verify_challenge(
            db,
            challenge_id=challenge_id,
            code="000000",
        )

    assert challenge.attempt_count == 1
    db.commit.assert_called_once()
    service.auth_manager.create_session.assert_not_called()


def test_expired_challenge_is_rejected():
    db = MagicMock()
    service = _service()
    service.auth_manager.get_challenge_for_update.return_value = SimpleNamespace(
        id=uuid4(),
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        attempt_count=0,
        consumed_at=None,
    )

    with pytest.raises(InvalidLoginChallengeError):
        service.verify_challenge(db, challenge_id=uuid4(), code="123456")

    service.auth_manager.create_session.assert_not_called()


def test_challenge_attempt_limit_is_enforced():
    db = MagicMock()
    service = _service()
    service.auth_manager.get_challenge_for_update.return_value = SimpleNamespace(
        id=uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        attempt_count=5,
        consumed_at=None,
    )

    with pytest.raises(InvalidLoginChallengeError):
        service.verify_challenge(db, challenge_id=uuid4(), code="123456")

    db.commit.assert_not_called()
    service.auth_manager.create_session.assert_not_called()


def test_expired_session_is_rejected():
    service = _service()
    service.auth_manager.find_session_by_token_hash.return_value = SimpleNamespace(
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        revoked_at=None,
    )

    with pytest.raises(InvalidSessionError):
        service.authenticate_session(MagicMock(), "expired-token")


def test_revoked_session_is_rejected():
    service = _service()
    service.auth_manager.find_session_by_token_hash.return_value = SimpleNamespace(
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        revoked_at=datetime.now(timezone.utc),
    )

    with pytest.raises(InvalidSessionError):
        service.authenticate_session(MagicMock(), "revoked-token")
