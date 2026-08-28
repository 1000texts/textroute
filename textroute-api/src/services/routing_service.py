"""Fan-out of an authorized message to its recipients.

Shared by both routes that reach delivery::

    moderator approves  -> approved        -> fan_out
    group policy allows -> auto_authorized -> fan_out

This service does not decide *whether* a message may be sent — callers
(``ModerationService`` for human review, ``InboundMessageService`` for policy
routing) establish that and record the appropriate status first. It owns the
delivery attempt and the resulting status bookkeeping only.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from src.core.managers.message_manager import MessageManager
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.core.providers.sms_provider import SmsProviderError
from src.domain.message_status import (
    PRE_DELIVERY_STATUSES,
    MessageWorkflowStatus,
)
from src.models import Group, Member, Message
from src.services.messaging_service import MessagingService

logger = logging.getLogger(__name__)


class RoutingError(Exception):
    """Delivery could not be attempted."""


class RoutingService:
    """Best-effort fan-out; continues after individual ``SmsProviderError``s."""

    def __init__(
        self,
        message_manager: MessageManager | None = None,
        phone_number_manager: PhoneNumberManager | None = None,
        messaging_service: MessagingService | None = None,
    ):
        self.message_manager = message_manager or MessageManager()
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.messaging_service = messaging_service or MessagingService(
            self.message_manager
        )

    def fan_out(
        self,
        db: Session,
        message: Message,
        recipients: list[Member],
    ) -> dict:
        """Send ``message.body`` unchanged to each recipient.

        Accepts any status in ``PRE_DELIVERY_STATUSES`` — both moderator-approved
        and policy-authorized messages are cleared for delivery, and this service
        deliberately does not distinguish them.
        """
        if message.workflow_status not in PRE_DELIVERY_STATUSES:
            raise RoutingError(
                f"Message is not cleared for delivery "
                f"(status={message.workflow_status})."
            )

        group = message.group
        if group is None:
            group = db.query(Group).filter(Group.id == message.group_id).one()

        from_number = self.resolve_from_number(db, group)
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.DELIVERING.value,
        )
        db.commit()

        delivered_ids: list[str] = []
        failures: list[dict] = []

        for recipient in recipients:
            try:
                outbound = self.messaging_service.send_message(
                    db,
                    group=group,
                    to_member=recipient,
                    from_phone_number=from_number,
                    body=message.body,  # original SMS unchanged
                    parent_message_id=message.id,
                )
                delivered_ids.append(str(outbound.id))
            except SmsProviderError as exc:
                failures.append(
                    {
                        "member_id": str(recipient.id),
                        "error": str(exc),
                    }
                )

        if failures and not delivered_ids:
            status = MessageWorkflowStatus.DELIVERY_FAILED.value
            notes = f"fanout_failed count={len(failures)}"
        elif failures:
            status = MessageWorkflowStatus.PARTIALLY_DELIVERED.value
            notes = (
                f"fanout_partial sent={len(delivered_ids)} "
                f"failed={len(failures)}"
            )
        else:
            status = MessageWorkflowStatus.DELIVERED.value
            notes = f"fanout_count={len(delivered_ids)}"

        self.message_manager.set_workflow_status(
            db,
            message,
            status,
            processing_notes=notes,
        )
        db.commit()

        return {
            "delivered_outbound_ids": delivered_ids,
            "delivery_failures": failures,
        }

    def resolve_from_number(self, db: Session, group: Group) -> str:
        numbers = self.phone_number_manager.list_for_group(db, group.id)
        assigned = [n for n in numbers if n.status == "assigned"]
        if not assigned:
            raise RoutingError("Group has no assigned TextRoute number.")
        return assigned[0].phone_number
