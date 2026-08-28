"""FastAPI request dependencies.

This module connects HTTP requests to authenticated application context.
It owns cookie/session wiring and HTTP 401 mapping; business services receive
the resulting ``ModeratorContext`` and do not authenticate themselves.
"""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from src.config.config import Config
from src.db.db import get_db
from src.services.auth_errors import InvalidSessionError
from src.services.auth_service import ModeratorAuthService, ModeratorContext


def get_moderator_context(
    request: Request,
    db: Session = Depends(get_db),
) -> ModeratorContext:
    token = request.cookies.get(Config.AUTH_COOKIE_NAME)
    try:
        return ModeratorAuthService().authenticate_session(db, token)
    except InvalidSessionError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
