from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Feedback(BaseModel):
    feedback_id: Optional[str] = Field(None, description="Unique ID for the feedback")
    feedback_type: str = Field(
        ..., description="Type of feedback (e.g., review, suggestion, complaint)"
    )
    rating: Optional[int] = Field(None, description="Optional rating value (e.g., 1–5)")
    description: str = Field(..., description="Feedback message or comments")
    created_by: Optional[str] = Field(
        None, description="User who submitted the feedback"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the feedback was submitted",
    )
    related_request_id: Optional[str] = Field(
        None, description="Optional reference to a related request"
    )
