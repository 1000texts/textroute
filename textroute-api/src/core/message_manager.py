from uuid import UUID

from sqlalchemy.orm import Session

from src.models import Message


class MessageManager:

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
    ) -> Message:
        """Insert an inbound message. Caller handles duplicates / commit."""
        message = Message(
            group_id=group_id,
            member_id=member_id,
            direction="inbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
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
    ) -> Message:
        message = Message(
            group_id=group_id,
            member_id=member_id,
            direction="outbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
        )
        db.add(message)
        db.flush()
        return message
