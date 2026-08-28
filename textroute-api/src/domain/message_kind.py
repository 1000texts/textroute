"""What an inbound message *is*, as distinct from what it is related to.

``parent_message_id`` represents message relationship, not moderation state. A
non-null parent does not by itself mean a message is exempt from moderation.
Finding a related original request and deciding moderation/routing policy are
separate concerns, so kind is decided explicitly here rather than inferred from
a foreign key.
"""

from enum import StrEnum


class InboundMessageKind(StrEnum):
    NEW_REQUEST = "new_request"
    REPLY = "reply"
    # Future: REPLY_WITH_NEW_REQUEST — "I have one. Also, anyone have a pressure
    # washer?" is both. Today such a message is handled only as a REPLY.


def determine_inbound_kind(
    *, has_original_request_candidate: bool
) -> InboundMessageKind:
    """Slice-only: presence of an original request candidate is the sole signal.

    Named ``determine`` rather than ``classify`` because no classification is
    happening yet — this is a timing-based inference, and calling it
    classification would make the eventual real analyzer sound like a no-op
    change.

    Takes a bool, not a message or parent id, so callers cannot re-derive kind
    from ``parent_message_id``. A future ``ReplyIntentAnalyzer`` (body semantics,
    "does this reply contain a new request?") replaces this function without
    touching the routing branch.
    """
    if has_original_request_candidate:
        return InboundMessageKind.REPLY
    return InboundMessageKind.NEW_REQUEST
