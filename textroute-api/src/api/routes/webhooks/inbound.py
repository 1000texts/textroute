"""Inbound SMS provider webhooks."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.phone_normalize import InvalidPhoneNumberError
from src.db.db import get_db
from src.schemas.api import IncomingMessageRequest
from src.services.inbound_errors import (
    DuplicateInboundMessageError,
    InboundMessageError,
    SenderNotInGroupError,
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
    UnknownSenderError,
)
from src.services.inbound_message_service import InboundMessageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/messages")
@router.post("/inbound")  # keep simulator-compatible path
def receive_message(
    request: IncomingMessageRequest,
    db: Session = Depends(get_db),
):
    service = InboundMessageService()
    try:
        return service.handle_incoming_message(
            db=db,
            from_phone_number=request.from_phone_number,
            to_phone_number=request.to_phone_number,
            body=request.body,
            provider_message_id=request.provider_message_id,
        )
    except InvalidPhoneNumberError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except DuplicateInboundMessageError as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"status": "duplicate", "message_id": e.message_id},
        ) from e
    except (
        UnknownReceivingNumberError,
        UnassignedPhoneNumberError,
        UnknownSenderError,
    ) as e:
        db.rollback()
        logger.warning("inbound_message_not_found", extra={"detail": str(e)})
        raise HTTPException(status_code=404, detail=str(e)) from e
    except SenderNotInGroupError as e:
        db.rollback()
        logger.warning("inbound_message_forbidden", extra={"detail": str(e)})
        raise HTTPException(status_code=403, detail=str(e)) from e
    except InboundMessageError as e:
        db.rollback()
        logger.warning("inbound_message_rejected", extra={"detail": str(e)})
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        db.rollback()
        logger.exception("inbound_message_unexpected_error")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None
