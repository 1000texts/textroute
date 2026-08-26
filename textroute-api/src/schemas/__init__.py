"""API DTOs and intent extraction schemas.

- ``schemas.api`` — HTTP request/response models for routes
- ``schemas.intent`` / ``schemas.registry`` — structured AI outputs (future MessageProcessor)
"""

from src.schemas.api import CreateGroupRequest, IncomingMessageRequest

__all__ = [
    "CreateGroupRequest",
    "IncomingMessageRequest",
]
