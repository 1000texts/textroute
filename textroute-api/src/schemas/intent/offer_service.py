from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class OfferService(BaseModel):
    offer_id: Optional[str] = Field(
        None, description="Unique ID for the service offer"
    )
    service_type: str = Field(
        ..., description="Type of service being offered"
    )
    description: Optional[str] = Field(
        None, description="Details about the service being offered"
    )
    available_slots: Optional[int] = Field(
        None, description="Number of people or slots available"
    )
    created_by: Optional[str] = Field(
        None, description="User offering the service"
    )
    start_date: Optional[datetime] = Field(
        None, description="Optional start date of availability (UTC)"
    )
    end_date: Optional[datetime] = Field(
        None, description="Optional end date of availability (UTC)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the offer was created",
    )
