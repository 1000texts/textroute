from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class BorrowRequest(BaseModel):
    request_id: Optional[str] = Field(
        None, description="Unique ID for the borrow request"
    )
    item_name: str = Field(..., description="Name of the item being requested")
    quantity: int = Field(1, description="Quantity of the item requested")
    purpose: Optional[str] = Field(
        None, description="Reason or purpose for borrowing the item"
    )
    borrow_date: Optional[datetime] = Field(
        None, description="Start date for borrowing (UTC)"
    )
    return_date: Optional[datetime] = Field(
        None, description="Expected return date (UTC)"
    )
    created_by: Optional[str] = Field(
        None, description="User submitting the borrow request"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the request was created",
    )
