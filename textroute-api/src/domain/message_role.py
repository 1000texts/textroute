"""What a message is, and who is speaking.

A message's meaning lives in two explicit columns, stamped once by whichever
path creates the row:

* ``sender_role`` -- member, moderator, or the system itself
* ``kind`` -- the role the message plays in its request

Neither may be re-derived downstream from ``request_id``,
``parent_message_id``, ``direction``, or timestamps. ``request_id`` expresses
parentage and nothing else: every message in a thread carries it, including the
original, so it cannot tell you what a message is.

Only five combinations are legal, and the database enforces them too
(``messages_role_shape_check``). ``member_id`` keeps its established meaning --
the member the row is *about* -- while ``author_member_id`` answers the
different question of who wrote it, and is NULL exactly when nobody did.
"""

from enum import StrEnum


class MessageSenderRole(StrEnum):
    MEMBER = "member"
    MODERATOR = "moderator"
    SYSTEM = "system"


class MessageKind(StrEnum):
    ORIGINAL_REQUEST = "original_request"
    MODERATOR_CLARIFICATION = "moderator_clarification"
    MEMBER_REPLY = "member_reply"
    FANOUT_COPY = "fanout_copy"
    CONFIRMATION = "confirmation"


# Kinds written by the person the row is about, so author and subject coincide.
_MEMBER_AUTHORED = frozenset(
    {
        MessageKind.ORIGINAL_REQUEST,
        MessageKind.MEMBER_REPLY,
        MessageKind.CONFIRMATION,
    }
)


# Kinds that make someone a party to the request rather than an actor on it:
# the requester who asked, the members fan-out reached, and anyone who answered.
#
# A moderator is deliberately absent. They act on a request without being in it,
# and a `moderator_clarification` names its recipient in `member_id` -- so
# counting participants asks `kind`, never `sender_role`, and never reads
# `author_member_id`, which is the only column a moderator appears in.
PARTICIPANT_KINDS = frozenset(
    {
        MessageKind.ORIGINAL_REQUEST,
        MessageKind.FANOUT_COPY,
        MessageKind.MEMBER_REPLY,
        MessageKind.CONFIRMATION,
    }
)


class InvalidMessageShapeError(ValueError):
    """The requested combination is not one of the five legal row shapes."""


def sender_role_for(kind: MessageKind) -> MessageSenderRole:
    """The one sender role a kind may carry.

    Callers pass a kind and get the role, rather than choosing both and hoping
    they agree.
    """
    if kind in _MEMBER_AUTHORED:
        return MessageSenderRole.MEMBER
    if kind is MessageKind.MODERATOR_CLARIFICATION:
        return MessageSenderRole.MODERATOR
    return MessageSenderRole.SYSTEM


def build_message_role(
    *,
    kind: MessageKind,
    member_id,
    author_member_id=None,
) -> dict:
    """Validate one row's shape and return the columns that express it.

    Every path that creates a message goes through here, so an illegal
    combination fails in the domain rather than surfacing as an IntegrityError
    from the check constraint. The two layers agree by construction; this one
    exists to give a readable error and a single place to read the rules.
    """
    role = sender_role_for(kind)

    if kind in _MEMBER_AUTHORED:
        if member_id is None:
            raise InvalidMessageShapeError(f"{kind} requires a member.")
        if author_member_id is not None and author_member_id != member_id:
            raise InvalidMessageShapeError(
                f"{kind} is written by its subject, so author and member "
                f"must be the same person."
            )
        author_member_id = member_id
    elif kind is MessageKind.MODERATOR_CLARIFICATION:
        if author_member_id is None:
            raise InvalidMessageShapeError(
                "A moderator clarification must record its author."
            )
    else:  # FANOUT_COPY
        if author_member_id is not None:
            raise InvalidMessageShapeError(
                "A fan-out copy has no author: the system generates it from a "
                "body someone else already wrote."
            )

    return {
        "kind": kind.value,
        "sender_role": role.value,
        "member_id": member_id,
        "author_member_id": author_member_id,
    }


def is_routable(kind: MessageKind | str | None) -> bool:
    """Whether this message is the thing a routing policy acts on.

    One predicate, one place. Because the answer comes from an explicit stamp
    rather than a derived fact, ``AUTO_GROUP`` cannot broadcast a reply even if
    a request linkage is later corrected by hand.
    """
    return kind == MessageKind.ORIGINAL_REQUEST


def determine_inbound_kind(*, joins_open_request: bool) -> MessageKind:
    """Decide, at the boundary, what an arriving SMS is.

    An inbound SMS is ``(from, to, body)`` with no thread identifier, so some
    decision here is unavoidable. What matters is that it is made **once**, at
    ingress, and immediately recorded in ``kind``; nothing downstream may work
    it out again from foreign keys or timing.

    The confirmation rule, deliberately narrow:

        ``confirmation`` is assigned only when the requester sends the inbound
        message that accompanies explicit request resolution. Other inbound
        messages remain ``member_reply`` regardless of their natural-language
        semantics.

    Do not "improve" this by adding keyword detection for "thanks" or "got
    one". "I have one" and "Great, thanks" are indistinguishable to any
    structural or timing rule, and guessing would put semantic inference back
    at the boundary that this design just removed it from. A future
    reply-intent analyzer may widen the rule as a deliberate decision; until
    then the narrowness is the point.
    """
    if joins_open_request:
        return MessageKind.MEMBER_REPLY
    return MessageKind.ORIGINAL_REQUEST


class RequestEventType(StrEnum):
    """Machine-generated activity on a request.

    A closed vocabulary; a seventh should be a deliberate migration.

    There is no ``partially_delivered``: delivery is recorded per recipient, so
    a partial fan-out is a mix of ``DELIVERED`` and ``DELIVERY_FAILED``. The
    aggregate stays on ``messages.workflow_status`` rather than being computed
    and stored in a second place where it could drift.
    """

    AUTHORIZED = "authorized"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
