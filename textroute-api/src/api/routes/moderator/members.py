"""Authenticated member-directory and member-enrollment routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.api.dependencies import get_moderator_context
from src.core.phone_normalize import InvalidPhoneNumberError
from src.db.db import get_db
from src.schemas.api import (
    AddMembersRequest,
    AddMembersResponse,
    AddedMemberResponse,
    UpdateMemberRequest,
)
from src.services.auth_service import ModeratorContext
from src.services.member_service import (
    DuplicateMemberPhoneError,
    LastModeratorError,
    MemberEnrollment,
    MemberNotFoundError,
    MemberService,
)

router = APIRouter(tags=["members"])


@router.get("/members")
def list_members(
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    return MemberService().list_members(db, group_id=context.group_id)


@router.patch("/members/{membership_id}")
def update_member(
    membership_id: UUID,
    request: UpdateMemberRequest,
    context: ModeratorContext = Depends(get_moderator_context),
    db: Session = Depends(get_db),
):
    """Edit one membership.

    ``group_id`` comes from the session rather than the request, so a moderator
    cannot edit a membership belonging to another group.
    """
    try:
        return MemberService().update_member(
            db,
            group_id=context.group_id,
            membership_id=membership_id,
            name=request.name,
            phone_number=request.phone_number,
            role=request.role,
            status=request.status,
        )
    except MemberNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (
        InvalidPhoneNumberError,
        DuplicateMemberPhoneError,
        LastModeratorError,
        ValueError,
    ) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred.",
        ) from None


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
