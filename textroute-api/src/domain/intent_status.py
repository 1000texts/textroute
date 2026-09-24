"""Whether a request's intent is usable yet.

Delivery does not read this. A group's routing policy decides if an original
message goes out. This status only tells a reply whether the description of
its parent request has been committed.
"""

from enum import StrEnum


class IntentStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


# Replies waiting on intent. Flipping this note is the claim, so the webhook
# and the worker cannot both record the same reply.
REPLY_DEFERRED = "reply_deferred"
REPLY_CLAIMED = "reply_claimed"
REPLY_RECORDED = "reply_recorded_unprocessed"


def intent_blocks_reply(status: str | None) -> bool:
    """True only for a real pending or failed status.

    Missing status is treated as ready so rows and test doubles that predate
    the column still record a reply instead of deferring forever.
    """
    return status in (IntentStatus.PENDING.value, IntentStatus.FAILED.value)
