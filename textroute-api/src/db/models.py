from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    String,
    func,
)

from src.models.base import Base
from src.models.requests import Requests

__all__ = ["InboundMessage", "Requests"]


class InboundMessage(Base):
    __tablename__ = "inbound_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String, nullable=False)
    receiver = Column(String, nullable=False)
    message = Column(String, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now())
