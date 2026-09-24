"""Moderator review + fan-out of the original inbound SMS body.

Callers (routes) must pass ``group_id`` from the authenticated session.
This service scopes every lookup to that group; it does not authenticate.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.managers.membership_manager import MembershipManager
from src.core.managers.message_manager import MessageManager
from src.core.managers.phone_number_manager import PhoneNumberManager
from src.core.managers.request_event_manager import RequestEventManager
from src.domain.message_role import RequestEventType
from src.domain.message_status import MessageWorkflowStatus
from src.models import Member, Message
from src.services.routing_service import RoutingError, RoutingService

logger = logging.getLogger(__name__)


class ModerationError(Exception):
    """Base moderation / delivery error."""


class MessageNotFoundError(ModerationError):
    pass


class InvalidModerationStateError(ModerationError):
    pass


class InvalidRecipientsError(ModerationError):
    pass


class ModerationService:
    """Human-in-the-loop: review suggestions, approve/reject.

    New routing requests default to a group-wide suggested audience; the
    moderator may narrow or expand recipients before send. Approve records the
    moderator's decision, then delegates delivery to ``RoutingService`` — the
    same fan-out used by policy-authorized routing.
    Per-recipient carrier receipts (``MessageDelivery``) are a follow-up.
    """

    def __init__(
        self,
        message_manager: MessageManager | None = None,
        membership_manager: MembershipManager | None = None,
        phone_number_manager: PhoneNumberManager | None = None,
        routing_service: RoutingService | None = None,
        request_event_manager: RequestEventManager | None = None,
    ):
        self.message_manager = message_manager or MessageManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.request_event_manager = request_event_manager or RequestEventManager()
        self.routing_service = routing_service or RoutingService(
            message_manager=self.message_manager,
            phone_number_manager=self.phone_number_manager,
            request_event_manager=self.request_event_manager,
        )

    def list_queue(self, db: Session, group_id: UUID) -> list[dict]:
        """Messages in ``awaiting_moderator`` for one group.

        The source of truth for the "needs review" count. Deliberately narrower
        than ``list_messages``: policy-routed messages were never queued.
        """
        messages = self.message_manager.list_inbound_for_group(
            db,
            group_id=group_id,
            statuses=[MessageWorkflowStatus.AWAITING_MODERATOR.value],
        )
        return [self._message_summary(db, m) for m in messages]

    def list_messages(
        self,
        db: Session,
        group_id: UUID,
        *,
        limit: int = 100,
    ) -> list[dict]:
        """Every inbound message for the group, whatever its workflow state.

        Feeds the moderator's general message list, which is not a moderation
        queue: most rows need no action. A future ``MessageQueryService`` could
        own this, but the summary helpers live here, so it stays for now.
        """
        messages = self.message_manager.list_inbound_for_group(
            db,
            group_id=group_id,
            limit=limit,
        )
        return [self._message_summary(db, m) for m in messages]

    def get_message(
        self,
        db: Session,
        message_id: UUID,
        *,
        group_id: UUID,
    ) -> dict:
        message = self._find_group_message(db, message_id, group_id)
        if message is None:
            raise MessageNotFoundError("Message not found.")
        return self._message_detail(db, message)

    def reject(
        self,
        db: Session,
        message_id: UUID,
        *,
        group_id: UUID,
    ) -> dict:
        message = self._require_awaiting(db, message_id, group_id)
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.MODERATOR_REJECTED.value,
            processing_notes="moderator_rejected",
        )
        # No request event, deliberately: the event vocabulary records what
        # happened *to* a request, and a rejection stops anything from
        # happening. It also leaves the request open, so the requester can still
        # be answered by hand or send something better.
        db.commit()
        return self._message_summary(db, message)

    def approve(
        self,
        db: Session,
        message_id: UUID,
        *,
        group_id: UUID,
        recipient_ids: list[UUID],
    ) -> dict:
        message = self._require_awaiting(db, message_id, group_id)
        if not recipient_ids:
            raise InvalidRecipientsError("At least one recipient is required.")

        # Deduplicated while preserving order: the list arrives from a browser,
        # and a repeated id would otherwise send the same person the same SMS
        # twice.
        unique_ids = list(dict.fromkeys(recipient_ids))
        # Routing a request back to the person who asked it is always a mistake,
        # and it would also make them a participant in their own fan-out.
        if message.member_id is not None and message.member_id in unique_ids:
            raise InvalidRecipientsError("Cannot route a message to its sender.")

        recipients = self._load_active_recipients(
            db,
            group_id=message.group_id,
            recipient_ids=unique_ids,
        )

        # Commit approval before fan-out so a mid-send crash still shows intent.
        self.message_manager.apply_approval(
            db,
            message,
            routed_recipient_ids=[m.id for m in recipients],
            workflow_status=MessageWorkflowStatus.APPROVED.value,
        )
        # Same event as policy routing, different payload: both authorize a
        # send, and the payload is where the audit trail says who or what did.
        if message.request_id is not None:
            self.request_event_manager.record(
                db,
                request_id=message.request_id,
                event_type=RequestEventType.AUTHORIZED,
                message_id=message.id,
                payload={
                    "by": "moderator",
                    "recipient_ids": [str(m.id) for m in recipients],
                },
            )
        db.commit()

        try:
            delivery = self.routing_service.fan_out(db, message, recipients)
        except RoutingError as exc:
            # Delivery could not even be attempted (no group number, say). The
            # approval above is already committed, so the moderator's decision
            # survives and the send can be retried once the cause is fixed.
            raise ModerationError(str(exc)) from exc

        # The caller is told what actually happened rather than that it was
        # approved: a fan-out can partially fail, and only fan_out knows.
        summary = self._message_summary(db, message)
        summary.update(delivery)
        return summary

    def _require_awaiting(
        self,
        db: Session,
        message_id: UUID,
        group_id: UUID,
    ) -> Message:
        message = self._find_group_message(db, message_id, group_id)
        if message is None:
            raise MessageNotFoundError("Message not found.")
        # The status is the guard against acting twice: two moderators with the
        # queue open both see the message, and whoever clicks second gets this
        # error rather than a second fan-out.
        if message.workflow_status != MessageWorkflowStatus.AWAITING_MODERATOR.value:
            raise InvalidModerationStateError(
                f"Message is not awaiting moderator "
                f"(status={message.workflow_status})."
            )
        return message

    def _find_group_message(
        self,
        db: Session,
        message_id: UUID,
        group_id: UUID,
    ) -> Message | None:
        """Cross-group ids look like not-found (no existence leak across groups)."""
        message = self.message_manager.find_by_id(db, message_id)
        if message is None or message.group_id != group_id:
            return None
        return message

    def _load_active_recipients(
        self,
        db: Session,
        *,
        group_id: UUID,
        recipient_ids: list[UUID],
    ) -> list[Member]:
        """Every id must resolve to an active member, or nothing is sent.

        Unlike policy routing, which skips anyone whose membership lapsed, a
        moderator named these people explicitly. Quietly dropping one would send
        to a different audience than the one they approved.
        """
        members: list[Member] = []
        for member_id in recipient_ids:
            membership = self.membership_manager.get_active_membership(
                db,
                member_id=member_id,
                group_id=group_id,
            )
            if membership is None or membership.member is None:
                raise InvalidRecipientsError(
                    f"Recipient {member_id} is not an active member of this group."
                )
            members.append(membership.member)
        return members

    def _member_brief(
        self,
        db: Session,
        member_id: UUID | None,
        group_id: UUID,
    ) -> dict | None:
        if member_id is None:
            return None
        member = db.query(Member).filter(Member.id == member_id).first()
        if member is None:
            # A deleted member still appears in stored recipient id lists, so
            # return the bare id rather than dropping the row and making the
            # audit trail disagree with itself about how many were sent to.
            return {"id": str(member_id)}
        membership = self.membership_manager.get_membership(
            db,
            member_id=member.id,
            group_id=group_id,
        )
        # A per-group display name wins over the member's global one: the same
        # person can be "Dad" in one group and "Ken Kahara" in another.
        profile = membership.profile if membership is not None else None
        return {
            "id": str(member.id),
            "name": profile.display_name if profile is not None else member.name,
            "phone_number": member.phone_number,
        }

    def _recipients_brief(
        self,
        db: Session,
        ids: list[UUID] | None,
        *,
        group_id: UUID,
        reasons: dict | None = None,
    ) -> list[dict]:
        if not ids:
            return []
        out: list[dict] = []
        for member_id in ids:
            brief = self._member_brief(db, member_id, group_id) or {
                "id": str(member_id)
            }
            # Looked up both ways because reasons may come from memory (UUID
            # keys) or from a JSONB column, which turns every key into a string.
            if reasons and member_id in reasons:
                brief["reason"] = reasons[member_id]
            elif reasons and str(member_id) in reasons:
                brief["reason"] = reasons[str(member_id)]
            else:
                label = brief.get("name") or brief.get("phone_number") or brief["id"]
                brief["reason"] = f"{label} — suggested"
            out.append(brief)
        return out

    def _message_summary(self, db: Session, message: Message) -> dict:
        return {
            "id": str(message.id),
            "group_id": str(message.group_id),
            "body": message.body,
            "workflow_status": message.workflow_status,
            # The analysis as it stood when this message was routed. The request
            # carries the current understanding; these two can diverge if a
            # request is re-analyzed, which is why both are kept.
            "intent": message.intent,
            "confidence": message.confidence,
            "constraints": message.constraints,
            "sender": self._member_brief(db, message.member_id, message.group_id),
            "suggested_recipients": self._recipients_brief(
                db,
                message.suggested_recipient_ids,
                group_id=message.group_id,
            ),
            "routed_recipients": self._recipients_brief(
                db,
                message.routed_recipient_ids,
                group_id=message.group_id,
            ),
            "sender_role": message.sender_role,
            "kind": message.kind,
            "routing_policy": message.routing_policy,
            # Lets the moderator open the whole conversation this belongs to.
            "request_id": message.request_id,
            "parent_message_id": (
                str(message.parent_message_id) if message.parent_message_id else None
            ),
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "processing_notes": message.processing_notes,
        }

    def _message_detail(self, db: Session, message: Message) -> dict:
        """The summary plus everyone the moderator could choose to send to.

        Only the detail view carries this, because it is what the approve form
        needs; the queue and feed would pay for the whole membership per row.
        """
        detail = self._message_summary(db, message)
        memberships = self.membership_manager.list_active_memberships(
            db, message.group_id
        )
        detail["eligible_recipients"] = [
            {
                "id": str(m.member.id),
                "name": (
                    m.profile.display_name
                    if m.profile is not None
                    else m.member.name
                ),
                "phone_number": m.member.phone_number,
                "role": m.role,
                # A hint the UI pre-ticks, not a decision: the model suggested
                # these, and the moderator is free to ignore every one.
                "suggested": (
                    message.suggested_recipient_ids is not None
                    and m.member.id in message.suggested_recipient_ids
                ),
            }
            for m in memberships
            # The sender is excluded here for the same reason approve() rejects
            # them, so the form cannot offer a choice the service would refuse.
            if m.member is not None and m.member_id != message.member_id
        ]
        return detail
