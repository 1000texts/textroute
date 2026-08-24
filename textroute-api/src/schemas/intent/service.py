from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ServiceRequest(BaseModel):
    request_id: Optional[str] = Field(
        None, description="Unique ID for the service request"
    )
    service_type: str = Field(
        ..., description="Type of service requested (e.g., transportation, cleaning)"
    )
    description: Optional[str] = Field(
        None, description="Detailed description of the service request"
    )
    priority: str = Field("normal", description="Priority level: low, normal, high")
    created_by: Optional[str] = Field(
        None, description="User who submitted the service request"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the request was created",
    )
    due_date: Optional[datetime] = Field(
        None, description="Requested completion date (UTC)"
    )
