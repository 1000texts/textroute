"""Explicit message workflow lifecycle.

Inbound routing messages move through these states. Outbound fan-out
copies typically stay at ``delivered`` (or ``delivery_failed``) since
they are delivery artifacts, not moderation subjects.
"""

from enum import StrEnum


class MessageWorkflowStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    AWAITING_MODERATOR = "awaiting_moderator"
    APPROVED = "approved"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    PROCESSING_FAILED = "processing_failed"
    MODERATOR_REJECTED = "moderator_rejected"
    DELIVERY_FAILED = "delivery_failed"


# Statuses that may still be acted on by a moderator
MODERATION_QUEUE_STATUSES = frozenset(
    {
        MessageWorkflowStatus.AWAITING_MODERATOR,
    }
)

# Terminal-ish statuses (no further automatic pipeline progress)
TERMINAL_STATUSES = frozenset(
    {
        MessageWorkflowStatus.DELIVERED,
        MessageWorkflowStatus.PROCESSING_FAILED,
        MessageWorkflowStatus.MODERATOR_REJECTED,
        MessageWorkflowStatus.DELIVERY_FAILED,
    }
)
