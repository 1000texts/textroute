from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.phone_normalize import InvalidPhoneNumberError
from src.db.db import get_db
from src.schemas.api import CreateGroupRequest
from src.services.group_service import GroupService

router = APIRouter(tags=["groups"])


@router.post("/groups")
def create_group(
    request: CreateGroupRequest,
    db: Session = Depends(get_db),
):
    try:
        return GroupService().create_group(
            db,
            name=request.name,
            description=request.description,
            moderator_phone_number=request.moderator_phone_number,
        )
    except InvalidPhoneNumberError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None
