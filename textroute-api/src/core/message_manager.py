from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from src.domain.message_status import MessageWorkflowStatus
from src.models import Message


class MessageManager:

    def find_by_id(self, db: Session, message_id: UUID) -> Message | None:
        return db.query(Message).filter(Message.id == message_id).first()

    def find_by_provider_message_id(
        self,
        db: Session,
        provider_message_id: str,
    ) -> Message | None:
        return (
            db.query(Message)
            .filter(Message.provider_message_id == provider_message_id)
            .first()
        )

    def list_by_workflow_status(
        self,
        db: Session,
        *,
        group_id: UUID,
        statuses: list[str],
        limit: int = 50,
    ) -> list[Message]:
        return (
            db.query(Message)
            .filter(
                Message.group_id == group_id,
                Message.direction == "inbound",
                Message.workflow_status.in_(statuses),
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )

    def find_recent_fanout_to_member(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
        within_hours: int = 72,
    ) -> Message | None:
        """Latest outbound fan-out copy delivered to this member (if any)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
        return (
            db.query(Message)
            .filter(
                Message.group_id == group_id,
                Message.member_id == member_id,
                Message.direction == "outbound",
                Message.parent_message_id.isnot(None),
                Message.created_at >= cutoff,
            )
            .order_by(Message.created_at.desc())
            .first()
        )

    def create_inbound(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
        from_phone_number: str,
        to_phone_number: str,
        body: str,
        provider_message_id: str | None = None,
        parent_message_id: UUID | None = None,
        workflow_status: str = MessageWorkflowStatus.RECEIVED.value,
    ) -> Message:
        """Insert an inbound message. Caller handles duplicates / commit."""
        message = Message(
            group_id=group_id,
            member_id=member_id,
            parent_message_id=parent_message_id,
            direction="inbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            workflow_status=workflow_status,
        )
        db.add(message)
        db.flush()
        return message

    def create_outbound(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID | None,
        from_phone_number: str,
        to_phone_number: str,
        body: str,
        provider_message_id: str | None = None,
        parent_message_id: UUID | None = None,
        workflow_status: str = MessageWorkflowStatus.SENT.value,
    ) -> Message:
        message = Message(
            group_id=group_id,
            member_id=member_id,
            parent_message_id=parent_message_id,
            direction="outbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            workflow_status=workflow_status,
        )
        db.add(message)
        db.flush()
        return message

    def set_workflow_status(
        self,
        db: Session,
        message: Message,
        status: str,
        *,
        processing_notes: str | None = None,
    ) -> Message:
        message.workflow_status = status
        if processing_notes is not None:
            message.processing_notes = processing_notes
        db.add(message)
        db.flush()
        return message

    def apply_processing_result(
        self,
        db: Session,
        message: Message,
        *,
        intent: str,
        constraints: dict | None,
        confidence: float | None,
        suggested_recipient_ids: list[UUID],
        notes: str | None,
        workflow_status: str = MessageWorkflowStatus.AWAITING_MODERATOR.value,
    ) -> Message:
        message.intent = intent
        message.constraints = constraints
        message.confidence = confidence
        message.suggested_recipient_ids = suggested_recipient_ids
        message.processing_notes = notes
        message.workflow_status = workflow_status
        db.add(message)
        db.flush()
        return message

    def apply_approval(
        self,
        db: Session,
        message: Message,
        *,
        approved_recipient_ids: list[UUID],
        workflow_status: str = MessageWorkflowStatus.APPROVED.value,
    ) -> Message:
        message.approved_recipient_ids = approved_recipient_ids
        message.workflow_status = workflow_status
        db.add(message)
        db.flush()
        return message
