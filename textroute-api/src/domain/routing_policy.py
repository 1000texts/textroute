"""Per-group routing policy for new requests.

A **moderator approves** a message; a **group policy authorizes** automatic
routing. These are different acts by different actors, so they never share a
status value or vocabulary — otherwise stored data ends up claiming a human
approved something no human ever saw.

This policy governs ``NEW_REQUEST`` only. Replies are never routed by policy
(see ``src.domain.message_role``).
"""

import logging
from enum import StrEnum

logger = logging.getLogger(__name__)


class RoutingPolicy(StrEnum):
    MODERATOR_REQUIRED = "moderator_required"
    AUTO_GROUP = "auto_group"
    # Reserved: accepted by the DB constraint so enabling it needs no schema
    # change, but not implemented. Falls back to moderation today.
    AUTO_MATCHED = "auto_matched"


IMPLEMENTED_POLICIES = frozenset(
    {
        RoutingPolicy.MODERATOR_REQUIRED,
        RoutingPolicy.AUTO_GROUP,
    }
)


def requires_moderation(raw: str | None) -> bool:
    """Fail safe: anything not explicitly auto-routing goes to a moderator.

    Unimplemented (``auto_matched``) and unrecognized values resolve to True.
    Never fail open into an unreviewed broadcast.
    """
    try:
        policy = RoutingPolicy(raw)
    except ValueError:
        logger.warning(
            "unknown_routing_policy_defaulting_to_moderation",
            extra={"routing_policy": raw},
        )
        return True

    if policy not in IMPLEMENTED_POLICIES:
        logger.warning(
            "unimplemented_routing_policy_defaulting_to_moderation",
            extra={"routing_policy": policy.value},
        )
        return True

    return policy is RoutingPolicy.MODERATOR_REQUIRED
