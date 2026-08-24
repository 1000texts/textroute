from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class StatusUpdate(BaseModel):
    update_id: Optional[str] = Field(
        None, description="Unique ID for the status update"
    )
    related_request_id: Optional[str] = Field(
        None, description="ID of the request being updated"
    )
    status: str = Field(
        ..., description="Current status (e.g., pending, in_progress, completed)"
    )
    description: Optional[str] = Field(
        None, description="Additional context or update message"
    )
    created_by: Optional[str] = Field(
        None, description="User who submitted the status update"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the update was created",
    )
