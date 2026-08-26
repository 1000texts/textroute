import logging

from sqlalchemy.orm import Session

from src.core.message_manager import MessageManager
from src.models import Group, Member, Message

logger = logging.getLogger(__name__)


class MessagingService:
    """Outbound SMS adapter.

    Provider-specific Twilio/TextRoute clients belong here later.
    For now this only records outbound Message rows.
    """

    def __init__(self, message_manager: MessageManager | None = None):
        self.message_manager = message_manager or MessageManager()

    def send_message(
        self,
        db: Session,
        *,
        group: Group,
        to_member: Member,
        from_phone_number: str,
        body: str,
    ) -> Message:
        logger.info(
            "outbound_message_queued",
            extra={
                "group_id": str(group.id),
                "member_id": str(to_member.id),
            },
        )
        # Provider send will go here. Persist outbound record for audit.
        return self.message_manager.create_outbound(
            db,
            group_id=group.id,
            member_id=to_member.id,
            from_phone_number=from_phone_number,
            to_phone_number=to_member.phone_number,
            body=body,
        )
