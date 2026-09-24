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


class ConversationMessageResponse(BaseModel):
    """One message as a handset would show it.

    ``direction`` places the bubble: inbound is what this member sent, outbound
    is what the group sent them. ``kind`` and ``workflow_status`` are along for
    debugging -- the point of the simulator is to watch how a message was
    classified and routed.

    ``body`` is exactly what TextRoute sent, verbatim. An outbound one already
    reads "Naruto: ..." because the sender is prefixed when the SMS is composed,
    so there is no separate sender field to render: adding one would invite a
    second, divergent label beside the text that already carries it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    direction: str
    body: str
    kind: str | None
    workflow_status: str
    created_at: datetime


class ConversationResponse(BaseModel):
    """A page of conversation plus the cursor to continue from.

    The cursor is the ``(created_at, id)`` of the last message rather than a
    timestamp alone: a fan-out writes its copies inside one transaction and they
    share a ``created_at`` exactly, so a timestamp-only cursor would step over
    the siblings and never return for them.
    """

    messages: list[ConversationMessageResponse]
    server_time: datetime


class CreateGroupRequest(BaseModel):
    name: str
    description: str | None = None
    moderator_phone_number: str
    moderator_name: str


class ApproveMessageRequest(BaseModel):
    recipient_ids: list[UUID]


class SendRequestMessageRequest(BaseModel):
    """A moderator speaking into a request thread.

    ``recipient_ids`` omitted means the requester alone, which is the usual case
    for a clarifying question.
    """

    body: str
    recipient_ids: list[UUID] | None = None


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


class UpdateMemberRequest(BaseModel):
    """A moderator's edit to one membership. All fields are sent every time."""

    name: str
    phone_number: str
    role: Literal["member", "moderator"]
    status: Literal["pending", "active", "declined", "removed", "opted_out"]
