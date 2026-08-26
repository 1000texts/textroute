from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from src.models import ModeratorLoginChallenge, ModeratorSession


class AuthManager:
    """Persistence helpers for moderator auth. Flush only; services commit."""

    def create_challenge(
        self,
        db: Session,
        *,
        challenge_id: UUID,
        group_id: UUID,
        moderator_member_id: UUID,
        code_hash: str,
        expires_at: datetime,
    ) -> ModeratorLoginChallenge:
        challenge = ModeratorLoginChallenge(
            id=challenge_id,
            group_id=group_id,
            moderator_member_id=moderator_member_id,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        db.add(challenge)
        db.flush()
        return challenge

    def get_challenge_for_update(
        self,
        db: Session,
        challenge_id: UUID,
    ) -> ModeratorLoginChallenge | None:
        return (
            db.query(ModeratorLoginChallenge)
            .filter(ModeratorLoginChallenge.id == challenge_id)
            .with_for_update()
            .first()
        )

    def create_session(
        self,
        db: Session,
        *,
        token_hash: str,
        group_id: UUID,
        moderator_member_id: UUID,
        expires_at: datetime,
    ) -> ModeratorSession:
        session = ModeratorSession(
            token_hash=token_hash,
            group_id=group_id,
            moderator_member_id=moderator_member_id,
            expires_at=expires_at,
        )
        db.add(session)
        db.flush()
        return session

    def find_session_by_token_hash(
        self,
        db: Session,
        token_hash: str,
    ) -> ModeratorSession | None:
        return (
            db.query(ModeratorSession)
            .filter(ModeratorSession.token_hash == token_hash)
            .first()
        )
