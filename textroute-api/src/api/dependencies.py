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
