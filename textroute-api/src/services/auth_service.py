"""Moderator passwordless login: SMS challenge → HttpOnly session cookie.

Stores HMAC hashes of codes/tokens only (never plaintext). Session scope is
one group; routes use ``ModeratorContext.group_id`` when calling other services.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.config.config import Config
from src.core.auth_manager import AuthManager
from src.core.membership_manager import MembershipManager
from src.core.phone_number_manager import PhoneNumberManager
from src.core.sms_provider import (
    SmsProvider,
    SmsProviderError,
    get_sms_provider,
)
from src.models import Group, Member, ModeratorSession
from src.services.auth_errors import (
    InvalidLoginChallengeError,
    InvalidModeratorCredentialsError,
    InvalidSessionError,
)


@dataclass(frozen=True)
class AuthSettings:
    secret: str
    challenge_ttl_seconds: int = 600
    session_ttl_seconds: int = 28_800
    max_attempts: int = 5
    expose_development_code: bool = False

    @classmethod
    def from_config(cls) -> AuthSettings:
        if not Config.AUTH_SECRET or len(Config.AUTH_SECRET) < 32:
            raise RuntimeError("AUTH_SECRET must contain at least 32 characters")
        return cls(
            secret=Config.AUTH_SECRET,
            challenge_ttl_seconds=Config.AUTH_CHALLENGE_TTL_SECONDS,
            session_ttl_seconds=Config.AUTH_SESSION_TTL_SECONDS,
            max_attempts=Config.AUTH_MAX_ATTEMPTS,
            expose_development_code=Config.AUTH_EXPOSE_DEVELOPMENT_CODE,
        )


@dataclass(frozen=True)
class ModeratorContext:
    session_id: UUID
    group_id: UUID
    moderator_member_id: UUID
    group_name: str
    group_phone_number: str
    expires_at: datetime


@dataclass(frozen=True)
class ChallengeResult:
    challenge_id: UUID
    expires_at: datetime
    development_code: str | None


@dataclass(frozen=True)
class VerificationResult:
    token: str
    context: ModeratorContext


class ModeratorAuthService:
    """Challenge + session lifecycle. Owns commits for auth writes."""

    def __init__(
        self,
        *,
        settings: AuthSettings | None = None,
        auth_manager: AuthManager | None = None,
        membership_manager: MembershipManager | None = None,
        phone_number_manager: PhoneNumberManager | None = None,
        sms_provider: SmsProvider | None = None,
    ):
        self.settings = settings or AuthSettings.from_config()
        self.auth_manager = auth_manager or AuthManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.sms_provider = sms_provider

    def request_challenge(
        self,
        db: Session,
        *,
        group_phone_number: str,
        moderator_phone_number: str,
    ) -> ChallengeResult:
        """Send a one-time code to the moderator's phone via ``SmsProvider``."""
        receiving_number = self.phone_number_manager.find_by_number(
            db,
            group_phone_number,
        )
        moderator = self.membership_manager.get_by_phone(
            db,
            moderator_phone_number,
        )
        # Same error for all failures — avoid account/group enumeration.
        if (
            receiving_number is None
            or receiving_number.status != "assigned"
            or receiving_number.group_id is None
            or moderator is None
        ):
            raise InvalidModeratorCredentialsError(
                "Unable to verify moderator credentials."
            )

        membership = self.membership_manager.get_active_membership(
            db,
            member_id=moderator.id,
            group_id=receiving_number.group_id,
        )
        if membership is None or membership.role != "moderator":
            raise InvalidModeratorCredentialsError(
                "Unable to verify moderator credentials."
            )

        challenge_id = uuid4()
        code = f"{secrets.randbelow(1_000_000):06d}"
        expires_at = self._now() + timedelta(
            seconds=self.settings.challenge_ttl_seconds
        )
        self.auth_manager.create_challenge(
            db,
            challenge_id=challenge_id,
            group_id=receiving_number.group_id,
            moderator_member_id=moderator.id,
            code_hash=self._hash_code(challenge_id, code),
            expires_at=expires_at,
        )
        try:
            provider = self.sms_provider or get_sms_provider()
            provider.send_sms(
                from_number=receiving_number.phone_number,
                to_number=moderator.phone_number,
                body=(
                    f"Your TextRoute moderator code is {code}. "
                    f"It expires in "
                    f"{self.settings.challenge_ttl_seconds // 60} minutes."
                ),
            )
        except Exception as error:
            raise SmsProviderError("Could not send confirmation code.") from error
        db.commit()
        return ChallengeResult(
            challenge_id=challenge_id,
            expires_at=expires_at,
            development_code=(
                code if self.settings.expose_development_code else None
            ),
        )

    def verify_challenge(
        self,
        db: Session,
        *,
        challenge_id: UUID,
        code: str,
    ) -> VerificationResult:
        """Consume challenge and return a raw session token (cookie value only)."""
        challenge = self.auth_manager.get_challenge_for_update(db, challenge_id)
        now = self._now()
        if (
            challenge is None
            or challenge.consumed_at is not None
            or challenge.expires_at <= now
            or challenge.attempt_count >= self.settings.max_attempts
        ):
            raise InvalidLoginChallengeError("Invalid or expired confirmation code.")

        if not hmac.compare_digest(
            challenge.code_hash,
            self._hash_code(challenge.id, code),
        ):
            challenge.attempt_count += 1
            db.add(challenge)
            db.commit()
            raise InvalidLoginChallengeError("Invalid or expired confirmation code.")

        challenge.consumed_at = now
        token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(seconds=self.settings.session_ttl_seconds)
        session = self.auth_manager.create_session(
            db,
            token_hash=self._hash_token(token),
            group_id=challenge.group_id,
            moderator_member_id=challenge.moderator_member_id,
            expires_at=expires_at,
        )
        db.add(challenge)
        db.commit()

        context = self._build_context(db, session)
        return VerificationResult(token=token, context=context)

    def authenticate_session(self, db: Session, token: str | None) -> ModeratorContext:
        """Resolve cookie token → group-scoped context (re-checks moderator role)."""
        if not token:
            raise InvalidSessionError("Authentication required.")
        session = self.auth_manager.find_session_by_token_hash(
            db,
            self._hash_token(token),
        )
        if (
            session is None
            or session.revoked_at is not None
            or session.expires_at <= self._now()
        ):
            raise InvalidSessionError("Authentication required.")
        return self._build_context(db, session)

    def logout(self, db: Session, token: str | None) -> None:
        if not token:
            return
        session = self.auth_manager.find_session_by_token_hash(
            db,
            self._hash_token(token),
        )
        if session is not None and session.revoked_at is None:
            session.revoked_at = self._now()
            db.add(session)
            db.commit()

    def _build_context(
        self,
        db: Session,
        session: ModeratorSession,
    ) -> ModeratorContext:
        group = db.query(Group).filter(Group.id == session.group_id).first()
        moderator = (
            db.query(Member)
            .filter(Member.id == session.moderator_member_id)
            .first()
        )
        membership = (
            self.membership_manager.get_active_membership(
                db,
                member_id=session.moderator_member_id,
                group_id=session.group_id,
            )
            if moderator is not None
            else None
        )
        phone_number = self.phone_number_manager.find_assigned_by_group(
            db,
            session.group_id,
        )
        if (
            group is None
            or moderator is None
            or membership is None
            or membership.role != "moderator"
            or phone_number is None
        ):
            raise InvalidSessionError("Authentication required.")
        return ModeratorContext(
            session_id=session.id,
            group_id=group.id,
            moderator_member_id=moderator.id,
            group_name=group.name,
            group_phone_number=phone_number.phone_number,
            expires_at=session.expires_at,
        )

    def _hash_code(self, challenge_id: UUID, code: str) -> str:
        # Bind code to challenge id so hashes are not reusable across rows.
        return self._hmac(f"code:{challenge_id}:{code}")

    def _hash_token(self, token: str) -> str:
        return self._hmac(f"session:{token}")

    def _hmac(self, value: str) -> str:
        return hmac.new(
            self.settings.secret.encode(),
            value.encode(),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
