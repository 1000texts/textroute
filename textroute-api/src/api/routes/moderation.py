from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.dependencies import get_moderator_context
from src.db.db import get_db
from src.schemas.api import ApproveMessageRequest
from src.services.auth_service import ModeratorContext
from src.services.moderation_service import (
    InvalidModerationStateError,
    InvalidRecipientsError,
    MessageNotFoundError,
    ModerationError,
    ModerationService,
)

router = APIRouter(tags=["moderation"])


@router.get("/moderation/queue")
def moderation_queue(
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    return ModerationService().list_queue(db, context.group_id)


@router.get("/messages/{message_id}")
def get_message(
    message_id: UUID,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    try:
        return ModerationService().get_message(
            db,
            message_id,
            group_id=context.group_id,
        )
    except MessageNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/messages/{message_id}/approve")
def approve_message(
    message_id: UUID,
    request: ApproveMessageRequest,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    try:
        return ModerationService().approve(
            db,
            message_id,
            group_id=context.group_id,
            recipient_ids=request.recipient_ids,
        )
    except MessageNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidModerationStateError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except InvalidRecipientsError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ModerationError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None


@router.post("/messages/{message_id}/reject")
def reject_message(
    message_id: UUID,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    try:
        return ModerationService().reject(
            db,
            message_id,
            group_id=context.group_id,
        )
    except MessageNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidModerationStateError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None
