from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class AnnouncementRequest(BaseModel):
    announcement_id: Optional[str] = Field(
        None, description="Unique ID for the announcement"
    )
    title: str = Field(..., description="Short title or headline of the announcement")
    description: str = Field(..., description="Full announcement content")
    audience: Optional[List[str]] = Field(
        None, description="Target audience groups or roles"
    )
    genre: str = Field(
        None,
        description="A category for the request in terms of interests and likemindeness",
    )
    created_by: Optional[str] = Field(
        None, description="User who posted the announcement"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the announcement was posted",
    )
    expires_at: Optional[datetime] = Field(
        None, description="Optional expiration datetime (UTC)"
    )
