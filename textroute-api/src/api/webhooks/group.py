from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.schemas import CreateGroupRequest
from src.core.group_manager import GroupManager
from src.core.membership_manager import MembershipManager
from src.core.phonenumber_manager import PhoneNumberManager
from src.db.db import get_db

router = APIRouter(tags=["groups"])


@router.post("/groups")
def create_group(
    request: CreateGroupRequest,
    db: Session = Depends(get_db),
):
    try:
        membership_manager = MembershipManager()
        group_manager = GroupManager()
        phone_number_manager = PhoneNumberManager()

        moderator = membership_manager.get_or_create_by_phone(
            db,
            request.moderator_phone_number,
        )

        group = group_manager.create_group(
            db=db,
            name=request.name,
            description=request.description,
        )

        membership_manager.join_group(
            db=db,
            member_id=moderator.id,
            group_id=group.id,
            role="moderator",
            status="active",
        )

        phone_number = phone_number_manager.assign_available_number(
            db=db,
            group_id=group.id,
        )

        db.commit()

        return {
            "id": str(group.id),
            "name": group.name,
            "description": group.description,
            "status": group.status,
            "moderator_member_id": str(moderator.id),
            "phone_number": phone_number.phone_number,
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=str(e),
        )

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        )
