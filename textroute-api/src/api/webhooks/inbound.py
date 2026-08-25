from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from src.api.schemas import InboundWebhookRequest
from src.db.db import get_db
from src.services.inbound import handle_inbound_message

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/inbound")
def inbound_webhook(request: Request, db: Session = Depends(get_db)):
    payload = InboundWebhookRequest.model_validate(request.json())
    return handle_inbound_message(
        db,
        sender=payload.sender,
        receiver=payload.receiver,
        body=payload.body,
    )
