"""Authenticated moderator routes for the request lifecycle.

Requests are the workflow objects; ``/messages`` remains the flat feed of what
arrived. A moderator reads a thread here, speaks into it, and closes it.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_moderator_context
from src.db.db import get_db
from src.schemas.api import SendRequestMessageRequest
from src.services.auth_service import ModeratorContext
from src.services.request_service import (
    NoRecipientsError,
    RequestError,
    RequestNotFoundError,
    RequestNotOpenError,
    RequestService,
)

router = APIRouter(tags=["requests"])


@router.get("/requests")
def list_requests(
    status: str | None = Query(default=None),
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    return RequestService().list_requests(
        db,
        context.group_id,
        statuses=[status] if status else None,
    )


@router.get("/requests/{request_id}")
def get_request(
    request_id: int,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    """One request with its full thread and audit trail."""
    try:
        return RequestService().get_request(
            db,
            request_id,
            group_id=context.group_id,
        )
    except RequestNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/requests/{request_id}/messages")
def send_request_message(
    request_id: int,
    request: SendRequestMessageRequest,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    """Send the moderator's own words into the thread."""
    try:
        return RequestService().send_moderator_message(
            db,
            request_id,
            group_id=context.group_id,
            author_member_id=context.moderator_member_id,
            body=request.body,
            recipient_ids=request.recipient_ids,
        )
    except RequestNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RequestNotOpenError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except (NoRecipientsError, RequestError) as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None


@router.post("/requests/{request_id}/complete")
def complete_request(
    request_id: int,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    return _resolve(db, RequestService().complete, request_id, context)


@router.post("/requests/{request_id}/cancel")
def cancel_request(
    request_id: int,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    return _resolve(db, RequestService().cancel, request_id, context)


def _resolve(db: Session, action, request_id: int, context: ModeratorContext):
    """Complete and cancel differ only in the transition they record."""
    try:
        return action(db, request_id, group_id=context.group_id)
    except RequestNotFoundError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except RequestNotOpenError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None
