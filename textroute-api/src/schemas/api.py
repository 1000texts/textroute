"""HTTP request/response DTOs for API routes."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IncomingMessageRequest(BaseModel):
    """Inbound SMS payload.

    Accepts simulator JSON (`from`/`to`/`body`) and Twilio-style
    (`From`/`To`/`Body`/`MessageSid`) field names.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_phone_number: str = Field(alias="from")
    to_phone_number: str = Field(alias="to")
    body: str
    provider_message_id: str | None = Field(default=None, alias="MessageSid")


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    moderator_phone_number: str


class ApproveMessageRequest(BaseModel):
    recipient_ids: list[UUID]


class UpdateRoutingPolicyRequest(BaseModel):
    """Unimplemented values are rejected by the service, not by this schema, so
    the error message can explain *why* rather than just listing valid strings."""

    routing_policy: str


class RequestModeratorChallenge(BaseModel):
    group_phone_number: str
    moderator_phone_number: str


class ModeratorChallengeResponse(BaseModel):
    challenge_id: UUID
    expires_at: datetime
    development_code: str | None = None


class VerifyModeratorChallenge(BaseModel):
    challenge_id: UUID
    code: str = Field(pattern=r"^\d{6}$")


class ModeratorSessionResponse(BaseModel):
    group_id: UUID
    moderator_member_id: UUID
    group_name: str
    group_phone_number: str
    expires_at: datetime


class MemberInput(BaseModel):
    phone_number: str = Field(min_length=1)
    name: str = Field(min_length=1, max_length=100)


class AddMembersRequest(BaseModel):
    members: list[MemberInput] = Field(min_length=1)
    consent_confirmed: Literal[True]


class AddedMemberResponse(BaseModel):
    member_id: UUID
    membership_id: UUID
    phone_number: str
    name: str


class AddMembersResponse(BaseModel):
    group_id: UUID
    members: list[AddedMemberResponse]
