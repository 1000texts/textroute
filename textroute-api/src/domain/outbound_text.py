"""What an outbound SMS actually says.

A member who receives a routed message sees only the group's TextRoute number.
Nothing in the SMS tells them who is asking, so the text has to:

    Naruto: Can anyone watch my dog this Sunday?
    Brother Mecham (Moderator): Could you clarify your question?

This is part of the message, not a display convention. It is composed once, on
the way out, so the provider payload and the stored ``messages.body`` are the
same string, and every reader -- a real handset, the simulator, the moderator UI,
an audit -- sees exactly what was sent.

Inbound messages are never touched. What a member wrote is what arrived.
"""

from src.domain.message_role import MessageKind


def sender_prefix(*, sender_name: str | None, kind: MessageKind | str) -> str:
    """``"Naruto: "``, or empty when there is nobody to name.

    A member with no ``name`` on record, or a fan-out copy whose author cannot be
    traced, sends the body unchanged. An unnamed prefix like ``": "`` would be
    worse than none.

    ``kind`` is compared as a string rather than looked up in a dict keyed by
    enum members: ``Enum.__hash__`` hashes the member *name*, so such a dict
    silently misses the equal string value.
    """
    name = (sender_name or "").strip()
    if not name:
        return ""

    # The one outbound kind whose author is not a fellow member. Recipients need
    # to know this came from whoever runs the group, not from a neighbour.
    suffix = (
        " (Moderator)" if str(kind) == MessageKind.MODERATOR_CLARIFICATION.value else ""
    )
    return f"{name}{suffix}: "


def with_sender(body: str, *, sender_name: str | None, kind: MessageKind | str) -> str:
    """The text to send, and to store as having been sent."""
    return f"{sender_prefix(sender_name=sender_name, kind=kind)}{body}"
