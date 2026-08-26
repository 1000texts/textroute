from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.core.phone_normalize import InvalidPhoneNumberError
from src.db.db import get_db
from src.schemas.api import AddMemberRequest, CreateGroupRequest
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


@router.post("/groups/{group_id}/members")
def add_group_member(
    group_id: UUID,
    request: AddMemberRequest,
    db: Session = Depends(get_db),
):
    try:
        return GroupService().add_member(
            db,
            group_id=group_id,
            phone_number=request.phone_number,
            name=request.name,
            role=request.role,
        )
    except LookupError as e:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(e)) from e
    except InvalidPhoneNumberError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None


@router.get("/groups/{group_id}/members")
def list_group_members(group_id: UUID, db: Session = Depends(get_db)):
    try:
        return GroupService().list_members(db, group_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
