"""Moderator review + fan-out delivery of the original inbound SMS body."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.membership_manager import MembershipManager
from src.core.message_manager import MessageManager
from src.core.phone_number_manager import PhoneNumberManager
from src.core.sms_provider import SmsProviderError
from src.domain.message_status import MessageWorkflowStatus
from src.models import Group, Member, Message
from src.services.messaging_service import MessagingService

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
    """Human-in-the-loop: review suggestions, approve/reject, fan out."""

    def __init__(
        self,
        message_manager: MessageManager | None = None,
        membership_manager: MembershipManager | None = None,
        phone_number_manager: PhoneNumberManager | None = None,
        messaging_service: MessagingService | None = None,
    ):
        self.message_manager = message_manager or MessageManager()
        self.membership_manager = membership_manager or MembershipManager()
        self.phone_number_manager = phone_number_manager or PhoneNumberManager()
        self.messaging_service = messaging_service or MessagingService(
            self.message_manager
        )

    def list_queue(self, db: Session, group_id: UUID) -> list[dict]:
        messages = self.message_manager.list_by_workflow_status(
            db,
            group_id=group_id,
            statuses=[MessageWorkflowStatus.AWAITING_MODERATOR.value],
        )
        return [self._message_summary(db, m) for m in messages]

    def get_message(self, db: Session, message_id: UUID) -> dict:
        message = self.message_manager.find_by_id(db, message_id)
        if message is None:
            raise MessageNotFoundError("Message not found.")
        return self._message_detail(db, message)

    def reject(self, db: Session, message_id: UUID) -> dict:
        message = self._require_awaiting(db, message_id)
        self.message_manager.set_workflow_status(
            db,
            message,
            MessageWorkflowStatus.MODERATOR_REJECTED.value,
            processing_notes="moderator_rejected",
        )
        db.commit()
        return self._message_summary(db, message)

    def approve(
        self,
        db: Session,
        message_id: UUID,
        *,
        recipient_ids: list[UUID],
    ) -> dict:
        message = self._require_awaiting(db, message_id)
        if not recipient_ids:
            raise InvalidRecipientsError("At least one recipient is required.")

        unique_ids = list(dict.fromkeys(recipient_ids))
        if message.member_id is not None and message.member_id in unique_ids:
            raise InvalidRecipientsError("Cannot route a message to its sender.")

        recipients = self._load_active_recipients(
            db,
            group_id=message.group_id,
            recipient_ids=unique_ids,
        )

        self.message_manager.apply_approval(
            db,
            message,
            approved_recipient_ids=[m.id for m in recipients],
            workflow_status=MessageWorkflowStatus.APPROVED.value,
        )
        db.commit()

        return self._deliver(db, message, recipients)

    def _deliver(
        self,
        db: Session,
        message: Message,
        recipients: list[Member],
    ) -> dict:
        group = message.group
        if group is None:
            group = db.query(Group).filter(Group.id == message.group_id).one()

        from_number = self._group_from_number(db, group)
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
        elif failures:
            status = MessageWorkflowStatus.DELIVERY_FAILED.value
            notes = f"partial_fanout failures={len(failures)}"
        else:
            status = MessageWorkflowStatus.DELIVERED.value
            notes = f"fanout_count={len(delivered_ids)}"

        if failures and delivered_ids:
            self.message_manager.set_workflow_status(
                db,
                message,
                status,
                processing_notes=notes,
            )
        elif failures:
            self.message_manager.set_workflow_status(
                db,
                message,
                status,
                processing_notes=f"fanout_failed count={len(failures)}",
            )
        else:
            self.message_manager.set_workflow_status(
                db,
                message,
                status,
                processing_notes=notes,
            )
        db.commit()

        summary = self._message_summary(db, message)
        summary["delivered_outbound_ids"] = delivered_ids
        summary["delivery_failures"] = failures
        return summary

    def _require_awaiting(self, db: Session, message_id: UUID) -> Message:
        message = self.message_manager.find_by_id(db, message_id)
        if message is None:
            raise MessageNotFoundError("Message not found.")
        if message.workflow_status != MessageWorkflowStatus.AWAITING_MODERATOR.value:
            raise InvalidModerationStateError(
                f"Message is not awaiting moderator "
                f"(status={message.workflow_status})."
            )
        return message

    def _load_active_recipients(
        self,
        db: Session,
        *,
        group_id: UUID,
        recipient_ids: list[UUID],
    ) -> list[Member]:
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

    def _group_from_number(self, db: Session, group: Group) -> str:
        numbers = self.phone_number_manager.list_for_group(db, group.id)
        assigned = [n for n in numbers if n.status == "assigned"]
        if not assigned:
            raise ModerationError("Group has no assigned TextRoute number.")
        return assigned[0].phone_number

    def _member_brief(self, db: Session, member_id: UUID | None) -> dict | None:
        if member_id is None:
            return None
        member = db.query(Member).filter(Member.id == member_id).first()
        if member is None:
            return {"id": str(member_id)}
        return {
            "id": str(member.id),
            "name": member.name,
            "phone_number": member.phone_number,
        }

    def _recipients_brief(
        self,
        db: Session,
        ids: list[UUID] | None,
        *,
        reasons: dict | None = None,
    ) -> list[dict]:
        if not ids:
            return []
        out: list[dict] = []
        for member_id in ids:
            brief = self._member_brief(db, member_id) or {"id": str(member_id)}
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
            "intent": message.intent,
            "confidence": message.confidence,
            "constraints": message.constraints,
            "sender": self._member_brief(db, message.member_id),
            "suggested_recipients": self._recipients_brief(
                db, message.suggested_recipient_ids
            ),
            "approved_recipients": self._recipients_brief(
                db, message.approved_recipient_ids
            ),
            "parent_message_id": (
                str(message.parent_message_id) if message.parent_message_id else None
            ),
            "created_at": message.created_at.isoformat() if message.created_at else None,
            "processing_notes": message.processing_notes,
        }

    def _message_detail(self, db: Session, message: Message) -> dict:
        detail = self._message_summary(db, message)
        memberships = self.membership_manager.list_active_memberships(
            db, message.group_id
        )
        detail["eligible_recipients"] = [
            {
                "id": str(m.member.id),
                "name": m.member.name,
                "phone_number": m.member.phone_number,
                "role": m.role,
                "suggested": (
                    message.suggested_recipient_ids is not None
                    and m.member.id in message.suggested_recipient_ids
                ),
            }
            for m in memberships
            if m.member is not None and m.member_id != message.member_id
        ]
        return detail
