from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Complaint(BaseModel):
    complaint_id: Optional[str] = Field(None, description="Unique ID for the complaint")
    title: str = Field(..., description="Short summary of the complaint")
    description: str = Field(..., description="Detailed explanation of the issue")
    urgency: Optional[str] = Field(None, description="Urgency level: low, normal, high")
    created_by: Optional[str] = Field(None, description="User submitting the complaint")
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the complaint was submitted",
    )
    related_request_id: Optional[str] = Field(
        None, description="Optional reference to a related request"
    )
