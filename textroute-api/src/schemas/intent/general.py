from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class GeneralRequest(BaseModel):
    request_id: Optional[str] = Field(None, description="Unique ID for the request")
    title: str = Field(..., description="Short subject or summary of the request")
    genre: str = Field(None, description="A category for the request in terms of interests and likemindeness")
    description: Optional[str] = Field(
        None, description="Detailed description of the request"
    )
    created_by: Optional[str] = Field(None, description="User submitting the request")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the request was created",
    )
