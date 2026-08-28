"""Explicit message workflow lifecycle.

Inbound routing messages move through these states. Successful outbound
fan-out copies use ``sent`` (provider accepted the send). A future
``MessageDelivery`` model can track per-recipient provider receipts.

Two distinct routes reach delivery, and the state machine keeps them distinct::

    awaiting_moderator -> approved        -> delivering -> delivered / ...
    received           -> auto_authorized -> delivering -> delivered / ...

``approved`` means a moderator acted. ``auto_authorized`` means a group routing
policy authorized automatic routing and no human reviewed the message. They
converge only at ``delivering``.
"""

from enum import StrEnum


class MessageWorkflowStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    AWAITING_MODERATOR = "awaiting_moderator"
    APPROVED = "approved"
    AUTO_AUTHORIZED = "auto_authorized"
    DELIVERING = "delivering"
    SENT = "sent"
    DELIVERED = "delivered"
    PARTIALLY_DELIVERED = "partially_delivered"
    PROCESSING_FAILED = "processing_failed"
    MODERATOR_REJECTED = "moderator_rejected"
    DELIVERY_FAILED = "delivery_failed"


# Statuses that may still be acted on by a moderator.
# Deliberately excludes AUTO_AUTHORIZED: policy-routed messages are not queued
# for review, and must never appear as if awaiting a human.
MODERATION_QUEUE_STATUSES = frozenset(
    {
        MessageWorkflowStatus.AWAITING_MODERATOR,
    }
)

# Cleared for fan-out. Both entries authorize delivery, but only APPROVED
# implies a moderator acted — callers needing that distinction must compare
# against APPROVED explicitly rather than testing membership here.
PRE_DELIVERY_STATUSES = frozenset(
    {
        MessageWorkflowStatus.APPROVED,
        MessageWorkflowStatus.AUTO_AUTHORIZED,
    }
)

# Terminal-ish statuses (no further automatic pipeline progress).
# AUTO_AUTHORIZED is transitional, like APPROVED, so it is absent here.
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
