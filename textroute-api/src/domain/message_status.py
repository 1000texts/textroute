"""Explicit message workflow lifecycle.

Inbound routing messages move through these states. Successful outbound
fan-out copies use ``sent`` (provider accepted the send). A future
``MessageDelivery`` model can track per-recipient provider receipts.
"""

from enum import StrEnum


class MessageWorkflowStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    AWAITING_MODERATOR = "awaiting_moderator"
    APPROVED = "approved"
    DELIVERING = "delivering"
    SENT = "sent"
    DELIVERED = "delivered"
    PARTIALLY_DELIVERED = "partially_delivered"
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
        MessageWorkflowStatus.SENT,
        MessageWorkflowStatus.DELIVERED,
        MessageWorkflowStatus.PARTIALLY_DELIVERED,
        MessageWorkflowStatus.PROCESSING_FAILED,
        MessageWorkflowStatus.MODERATOR_REJECTED,
        MessageWorkflowStatus.DELIVERY_FAILED,
    }
)
