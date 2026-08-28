"""Moderator web-app authentication routes.

Challenge and verification start unauthenticated; session, logout, and
moderator context are managed through the cookie-based auth flow.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from src.api.dependencies import get_moderator_context
from src.config.config import Config
from src.core.providers.sms_provider import SmsProviderError
from src.db.db import get_db
from src.schemas.api import (
    ModeratorChallengeResponse,
    ModeratorSessionResponse,
    RequestModeratorChallenge,
    VerifyModeratorChallenge,
)
from src.services.auth_errors import AuthenticationError
from src.services.auth_service import ModeratorAuthService, ModeratorContext

router = APIRouter(prefix="/auth", tags=["moderator-auth"])


def _session_response(context: ModeratorContext) -> ModeratorSessionResponse:
    return ModeratorSessionResponse(
        group_id=context.group_id,
        moderator_member_id=context.moderator_member_id,
        group_name=context.group_name,
        group_phone_number=context.group_phone_number,
        expires_at=context.expires_at,
    )


@router.post("/challenge", response_model=ModeratorChallengeResponse)
def request_challenge(
    request: RequestModeratorChallenge,
    db: Session = Depends(get_db),
):
    try:
        result = ModeratorAuthService().request_challenge(
            db,
            group_phone_number=request.group_phone_number,
            moderator_phone_number=request.moderator_phone_number,
        )
    except SmsProviderError as error:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Could not send confirmation code.",
        ) from error
    except (AuthenticationError, ValueError) as error:
        db.rollback()
        raise HTTPException(
            status_code=401,
            detail="Unable to verify moderator credentials.",
        ) from error
    return ModeratorChallengeResponse(
        challenge_id=result.challenge_id,
        expires_at=result.expires_at,
        development_code=result.development_code,
    )


@router.post("/verify", response_model=ModeratorSessionResponse)
def verify_challenge(
    request: VerifyModeratorChallenge,
    response: Response,
    db: Session = Depends(get_db),
):
    try:
        result = ModeratorAuthService().verify_challenge(
            db,
            challenge_id=request.challenge_id,
            code=request.code,
        )
    except AuthenticationError as error:
        db.rollback()
        raise HTTPException(status_code=401, detail=str(error)) from error

    response.set_cookie(
        key=Config.AUTH_COOKIE_NAME,
        value=result.token,
        max_age=Config.AUTH_SESSION_TTL_SECONDS,
        httponly=True,
        secure=Config.AUTH_COOKIE_SECURE,
        # SameSite=Lax: deliberate CSRF stance for same-site UI↔API. See README.
        samesite="lax",
        path="/",
    )
    return _session_response(result.context)


@router.get("/session", response_model=ModeratorSessionResponse)
def get_session(
    context: ModeratorContext = Depends(get_moderator_context),
):
    return _session_response(context)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    ModeratorAuthService().logout(
        db,
        request.cookies.get(Config.AUTH_COOKIE_NAME),
    )
    response.delete_cookie(
        key=Config.AUTH_COOKIE_NAME,
        httponly=True,
        secure=Config.AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
