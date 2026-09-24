"""Read a handset's conversation, for the SMS simulator.

A read rather than a provider callback, but it lives under ``/webhook`` on
purpose. The simulator's only credential is the webhook shared secret, and the
production nginx vhost injects that secret for ``/api/webhook/`` and nothing
else, deliberately:

    # Only the webhook is reachable through this origin. Scoping it here means
    # the injected secret can never ride along with some other API call.

Putting the route here means the simulator can reach it with the credential it
already holds and no widening of that scope.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.dependencies import verify_webhook_secret
from src.core.phone_normalize import InvalidPhoneNumberError
from src.db.db import get_db
from src.schemas.api import ConversationResponse
from src.services.inbound_errors import (
    UnassignedPhoneNumberError,
    UnknownReceivingNumberError,
)
from src.services.simulator_service import SimulatorService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhook",
    tags=["webhooks"],
    # Applied at the router so a future webhook route cannot be added unguarded.
    dependencies=[Depends(verify_webhook_secret)],
)


@router.get("/conversation", response_model=ConversationResponse)
def read_conversation(
    from_phone_number: str = Query(alias="from"),
    to_phone_number: str = Query(alias="to"),
    after_created_at: datetime | None = Query(default=None),
    after_id: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Messages between one member's number and one group's number.

    ``from``/``to`` match the inbound webhook's field names, so the simulator
    sends the same pair whether it is reading or writing.

    Both cursor halves or neither: half a cursor is a caller bug, and silently
    ignoring it would show a full reload as if it were a page of new messages.
    """
    if (after_created_at is None) != (after_id is None):
        raise HTTPException(
            status_code=400,
            detail="after_created_at and after_id must be given together.",
        )

    try:
        messages = SimulatorService().load_conversation(
            db,
            member_phone_number=from_phone_number,
            group_phone_number=to_phone_number,
            after_created_at=after_created_at,
            after_id=after_id,
        )
    except InvalidPhoneNumberError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (UnknownReceivingNumberError, UnassignedPhoneNumberError) as e:
        logger.warning("conversation_number_not_found", extra={"detail": str(e)})
        raise HTTPException(status_code=404, detail=str(e)) from e

    return ConversationResponse(
        messages=messages,
        # Returned so the simulator can show drift between its own clock and
        # the server's rather than guessing why a message looks out of order.
        server_time=datetime.now(timezone.utc),
    )
