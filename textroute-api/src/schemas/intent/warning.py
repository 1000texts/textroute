from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class Warning(BaseModel):
    warning_id: Optional[str] = Field(None, description="Unique ID for the warning")
    title: str = Field(..., description="Short title of the warning")
    description: str = Field(..., description="Detailed warning message")
    severity: str = Field(
        ..., description="Severity level: low, medium, high, critical"
    )
    affected_areas: Optional[List[str]] = Field(
        None, description="Areas, locations, or systems affected"
    )
    created_by: Optional[str] = Field(
        None, description="User or system issuing the warning"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the warning was issued",
    )
    expires_at: Optional[datetime] = Field(
        None, description="Optional expiration datetime (UTC)"
    )
