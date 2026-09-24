"""Outbound SMS: provider send first, then persist a ``sent`` outbound row.

Used by moderation fan-out (and future automated sends). Callers own the
surrounding transaction/commit for multi-recipient loops.

The text sent is the caller's body with its sender prefixed (see
``src.domain.outbound_text``), because a recipient sees only the group's number
and would otherwise have no idea who is speaking. The same composed string is
sent and stored.
"""

import logging

from sqlalchemy.orm import Session

from src.core.managers.message_manager import MessageManager
from src.core.providers.sms_provider import (
    SmsProvider,
    SmsProviderError,
    get_sms_provider,
)
from src.domain.message_role import MessageKind
from src.domain.message_status import MessageWorkflowStatus
from src.domain.outbound_text import with_sender
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
        kind: MessageKind,
        sender_name: str | None = None,
        author_member_id=None,
        request_id: int | None = None,
        parent_message_id=None,
    ) -> Message:
        """Send one SMS and record it.

        ``kind`` says what is being sent: a ``fanout_copy`` the system generated
        from someone else's words, or a ``moderator_clarification`` a person
        wrote. The two differ in whether ``author_member_id`` is set, which the
        role shape enforces.

        ``sender_name`` is whoever the recipient should see this as being from,
        and is prefixed to the text. It is not always the ``author_member_id``:
        a fan-out copy must have no author, yet it carries a member's words and
        has to say whose. Callers supply the name because only they can trace it.
        """
        # Composed once, here, so the string handed to the provider is the string
        # persisted. Doing it in the provider would leave the stored row claiming
        # something else was sent; doing it per caller would let one path drift.
        text = with_sender(body, sender_name=sender_name, kind=kind)
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
                body=text,
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
            kind=kind,
            author_member_id=author_member_id,
            request_id=request_id,
            from_phone_number=from_phone_number,
            to_phone_number=to_member.phone_number,
            body=text,
            provider_message_id=provider_message_id,
            parent_message_id=parent_message_id,
            workflow_status=MessageWorkflowStatus.SENT.value,
        )
