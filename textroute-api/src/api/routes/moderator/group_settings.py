"""Authenticated group settings, including the routing policy."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.dependencies import get_moderator_context
from src.db.db import get_db
from src.schemas.api import UpdateRoutingPolicyRequest
from src.services.auth_service import ModeratorContext
from src.services.group_service import (
    GroupService,
    UnsupportedRoutingPolicyError,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["groups"])


@router.get("/group/settings")
def get_group_settings(
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    try:
        return GroupService().get_settings(db, context.group_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/group/settings")
def update_group_settings(
    request: UpdateRoutingPolicyRequest,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    try:
        return GroupService().set_routing_policy(
            db,
            context.group_id,
            routing_policy=request.routing_policy,
        )
    except UnsupportedRoutingPolicyError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception:
        db.rollback()
        logger.exception("update_group_settings_failed")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None
