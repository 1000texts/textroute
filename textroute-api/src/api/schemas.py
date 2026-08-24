from pydantic import BaseModel, ConfigDict, Field


class InboundWebhookRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sender: str = Field(alias="from")
    receiver: str = Field(alias="to")
    body: str
