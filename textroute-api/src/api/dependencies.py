"""FastAPI request dependencies.

This module connects HTTP requests to authenticated application context.
It owns cookie/session wiring and HTTP 401 mapping; business services receive
the resulting ``ModeratorContext`` and do not authenticate themselves.
"""

import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.config.config import Config
from src.db.db import get_db
from src.services.auth_errors import InvalidSessionError
from src.services.auth_service import ModeratorAuthService, ModeratorContext

WEBHOOK_SECRET_HEADER = "X-Webhook-Secret"


def get_moderator_context(
    request: Request,
    db: Session = Depends(get_db),
) -> ModeratorContext:
    token = request.cookies.get(Config.AUTH_COOKIE_NAME)
    try:
        return ModeratorAuthService().authenticate_session(db, token)
    except InvalidSessionError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


def verify_webhook_secret(request: Request) -> None:
    """Reject webhook calls that do not carry the shared secret.

    Anyone who learns the public API URL could otherwise forge an inbound SMS
    into a real group, which under the ``auto_group`` routing policy fans out
    real messages to real people. Real carriers sign their requests; this is the
    placeholder until provider-specific signature verification exists, and the
    swap touches only this function.

    Unset ``WEBHOOK_SECRET`` fails closed rather than silently disabling the
    check, so a misconfigured deployment is unreachable instead of open.
    """
    expected = Config.WEBHOOK_SECRET
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Webhook endpoint is not configured.",
        )

    provided = request.headers.get(WEBHOOK_SECRET_HEADER)
    # compare_digest keeps the comparison time independent of how many leading
    # characters happen to match.
    if provided is None or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook credentials.")
