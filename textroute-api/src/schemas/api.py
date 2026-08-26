"""HTTP request/response DTOs for API routes."""

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
