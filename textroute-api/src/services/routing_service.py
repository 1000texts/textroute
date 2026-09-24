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

from src.core.managers.membership_manager import MembershipManager
from src.core.managers.message_manager import MessageManager
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.core.managers.request_event_manager import RequestEventManager
from src.core.providers.sms_provider import SmsProviderError
from src.domain.message_role import MessageKind, RequestEventType
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
        request_event_manager: RequestEventManager | None = None,
        membership_manager: MembershipManager | None = None,
    ):
        self.message_manager = message_manager or MessageManager()
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.request_event_manager = request_event_manager or RequestEventManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.messaging_service = messaging_service or MessagingService(
            self.message_manager
        )

    def fan_out(
        self,
        db: Session,
        message: Message,
        recipients: list[Member],
    ) -> dict:
        """Send ``message.body`` to each recipient, credited to whoever wrote it.

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

        # Whose words these are. The copy itself must have no author -- nobody
        # wrote it, the system reproduced it -- so the name comes from the message
        # being fanned out, resolved once rather than per recipient.
        #
        # Group-scoped rather than ``message.author.name``: a member may be known
        # by a different name in this group, and the SMS should use the one the
        # group knows them by.
        sender_name = None
        if message.author_member_id is not None:
            sender_name = self.membership_manager.get_display_names(
                db,
                group_id=group.id,
                member_ids=[message.author_member_id],
            ).get(message.author_member_id)

        for recipient in recipients:
            try:
                # The copy is a system artefact: it carries the recipient in
                # member_id and no author. The body is the requester's words,
                # with their name prefixed, because the recipient sees only the
                # group's number and nothing else would say who is asking.
                outbound = self.messaging_service.send_message(
                    db,
                    group=group,
                    to_member=recipient,
                    from_phone_number=from_number,
                    body=message.body,
                    sender_name=sender_name,
                    kind=MessageKind.FANOUT_COPY,
                    request_id=message.request_id,
                    parent_message_id=message.id,
                )
                delivered_ids.append(str(outbound.id))
                self._record_delivery(
                    db,
                    request_id=message.request_id,
                    event_type=RequestEventType.DELIVERED,
                    message_id=outbound.id,
                    payload={"member_id": str(recipient.id)},
                )
            except SmsProviderError as exc:
                failures.append(
                    {
                        "member_id": str(recipient.id),
                        "error": str(exc),
                    }
                )
                # No outbound row exists to point at: the send never happened.
                self._record_delivery(
                    db,
                    request_id=message.request_id,
                    event_type=RequestEventType.DELIVERY_FAILED,
                    message_id=None,
                    payload={"member_id": str(recipient.id), "error": str(exc)},
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

    def _record_delivery(
        self,
        db: Session,
        *,
        request_id: int | None,
        event_type: RequestEventType,
        message_id,
        payload: dict,
    ) -> None:
        """One event per recipient, which is what makes a partial fan-out legible.

        The aggregate lives on ``messages.workflow_status``; these say who
        actually got it. Fan-out predates requests in some rows, so a message
        without one simply records no event rather than failing the send.
        """
        if request_id is None:
            return
        self.request_event_manager.record(
            db,
            request_id=request_id,
            event_type=event_type,
            message_id=message_id,
            payload=payload,
        )

    def resolve_from_number(self, db: Session, group: Group) -> str:
        numbers = self.phone_number_manager.list_for_group(db, group.id)
        assigned = [n for n in numbers if n.status == "assigned"]
        if not assigned:
            raise RoutingError("Group has no assigned TextRoute number.")
        return assigned[0].phone_number
