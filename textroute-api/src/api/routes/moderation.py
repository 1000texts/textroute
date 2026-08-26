from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.db.db import get_db
from src.schemas.api import ApproveMessageRequest
from src.services.moderation_service import (
    InvalidModerationStateError,
    InvalidRecipientsError,
    MessageNotFoundError,
    ModerationError,
    ModerationService,
)

router = APIRouter(tags=["moderation"])


@router.get("/groups/{group_id}/moderation/queue")
def moderation_queue(group_id: UUID, db: Session = Depends(get_db)):
    return ModerationService().list_queue(db, group_id)


@router.get("/messages/{message_id}")
def get_message(message_id: UUID, db: Session = Depends(get_db)):
    try:
        return ModerationService().get_message(db, message_id)
    except MessageNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/messages/{message_id}/approve")
def approve_message(
    message_id: UUID,
    request: ApproveMessageRequest,
    db: Session = Depends(get_db),
):
    try:
        return ModerationService().approve(
            db,
            message_id,
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
def reject_message(message_id: UUID, db: Session = Depends(get_db)):
    try:
        return ModerationService().reject(db, message_id)
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
