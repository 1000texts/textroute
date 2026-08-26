"""Outbound SMS: provider send first, then persist a ``sent`` outbound row.

Used by moderation fan-out (and future automated sends). Callers own the
surrounding transaction/commit for multi-recipient loops.
"""

import logging

from sqlalchemy.orm import Session

from src.core.message_manager import MessageManager
from src.core.sms_provider import SmsProvider, SmsProviderError, get_sms_provider
from src.domain.message_status import MessageWorkflowStatus
from src.models import Group, Member, Message

logger = logging.getLogger(__name__)


class MessagingService:
    """Outbound SMS orchestration.

    Order matters: call ``SmsProvider`` before writing the outbound row so a
    provider failure leaves no orphan message. ``SmsProviderError`` passes
    through unchanged; other exceptions are not wrapped here.
    Successful sends use workflow status ``sent`` (provider accepted), not
    carrier delivery confirmation.
    """

    def __init__(
        self,
        message_manager: MessageManager | None = None,
        sms_provider: SmsProvider | None = None,
    ):
        self.message_manager = message_manager or MessageManager()
        self.sms_provider = sms_provider or get_sms_provider()

    def send_message(
        self,
        db: Session,
        *,
        group: Group,
        to_member: Member,
        from_phone_number: str,
        body: str,
        parent_message_id=None,
    ) -> Message:
        logger.info(
            "outbound_message_sending",
            extra={
                "group_id": str(group.id),
                "member_id": str(to_member.id),
            },
        )
        try:
            provider_message_id = self.sms_provider.send_sms(
                from_number=from_phone_number,
                to_number=to_member.phone_number,
                body=body,
            )
        except SmsProviderError:
            logger.exception(
                "outbound_message_provider_failed",
                extra={
                    "group_id": str(group.id),
                    "member_id": str(to_member.id),
                },
            )
            raise

        return self.message_manager.create_outbound(
            db,
            group_id=group.id,
            member_id=to_member.id,
            from_phone_number=from_phone_number,
            to_phone_number=to_member.phone_number,
            body=body,
            provider_message_id=provider_message_id,
            parent_message_id=parent_message_id,
            workflow_status=MessageWorkflowStatus.SENT.value,
        )
