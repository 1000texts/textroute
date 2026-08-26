from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.dependencies import get_moderator_context
from src.core.phone_normalize import InvalidPhoneNumberError
from src.db.db import get_db
from src.schemas.api import (
    AddMembersRequest,
    AddMembersResponse,
    AddedMemberResponse,
)
from src.services.auth_service import ModeratorContext
from src.services.member_service import (
    DuplicateMemberPhoneError,
    MemberEnrollment,
    MemberService,
)

router = APIRouter(tags=["members"])


@router.get("/members")
def list_members(
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    return MemberService().list_members(db, group_id=context.group_id)


@router.post("/members", response_model=AddMembersResponse)
def add_members(
    request: AddMembersRequest,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    try:
        added = MemberService().add_members(
            db,
            group_id=context.group_id,
            enrollments=[
                MemberEnrollment(
                    phone_number=member.phone_number,
                    name=member.name,
                )
                for member in request.members
            ],
        )
    except (InvalidPhoneNumberError, DuplicateMemberPhoneError, ValueError) as error:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None

    return AddMembersResponse(
        group_id=context.group_id,
        members=[
            AddedMemberResponse(
                member_id=member.member_id,
                membership_id=member.membership_id,
                phone_number=member.phone_number,
                name=member.name,
            )
            for member in added
        ],
    )
