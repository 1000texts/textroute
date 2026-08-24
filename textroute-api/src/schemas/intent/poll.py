from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Poll(BaseModel):
    poll_id: Optional[str] = Field(None, description="Unique ID for the poll")
    question: str = Field(..., description="Poll question presented to users")
    options: List[str] = Field(..., description="List of selectable answer options")
    multiple_selection: bool = Field(
        False, description="Whether multiple options can be selected"
    )
    audience: str = Field(
        ...,
        description="Intended group of participants for the poll, such as a role, interest, or segment",
    )
    created_by: Optional[str] = Field(None, description="User who created the poll")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the poll was created",
    )
    expires_at: Optional[datetime] = Field(
        None, description="Optional poll expiration datetime (UTC)"
    )
