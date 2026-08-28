"""Application services — use-case orchestration and transaction ownership.

Layer contract for contributors:
- Routes: HTTP + auth; pass ``group_id`` from the session into services.
- Services: own business ``db.commit()`` / ``db.rollback()``; raise domain errors.
- Managers (``core/*``): persistence helpers that flush only; no commits.
- Do not put authentication or HTTP status mapping inside services.

Routes may issue a defensive rollback while converting an exception to HTTP,
but they must not commit or split a service's business transaction.
"""

from src.services.auth_service import ModeratorAuthService
from src.services.group_service import GroupService
from src.services.inbound_message_service import InboundMessageService
from src.services.member_service import MemberService
from src.services.messaging_service import MessagingService
from src.services.moderation_service import ModerationService

__all__ = [
    "GroupService",
    "InboundMessageService",
    "MemberService",
    "MessagingService",
    "ModeratorAuthService",
    "ModerationService",
]
