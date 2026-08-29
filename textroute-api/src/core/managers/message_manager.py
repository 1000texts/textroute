from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.domain.message_role import MessageKind, build_message_role
from src.domain.message_status import MessageWorkflowStatus
from src.models import Message, Requests


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

    def list_inbound_for_group(
        self,
        db: Session,
        *,
        group_id: UUID,
        statuses: list[str] | None = None,
        limit: int = 100,
    ) -> list[Message]:
        """Inbound messages for one group, newest first.

        Outbound fan-out copies are excluded from the moderator message feed:
        they are delivery records, not things a moderator reads. Delivery
        surfaces through the selected message's detail view (routed recipients
        plus the aggregate delivered / partially_delivered status).

        ``statuses=None`` returns every workflow state.
        """
        query = db.query(Message).filter(
            Message.group_id == group_id,
            Message.direction == "inbound",
        )
        if statuses is not None:
            query = query.filter(Message.workflow_status.in_(statuses))
        return query.order_by(Message.created_at.desc()).limit(limit).all()

    def create_inbound(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
        kind: MessageKind,
        request_id: int | None = None,
        from_phone_number: str,
        to_phone_number: str,
        body: str,
        provider_message_id: str | None = None,
        parent_message_id: UUID | None = None,
        workflow_status: str = MessageWorkflowStatus.RECEIVED.value,
    ) -> Message:
        """Insert an inbound message. Caller handles duplicates / commit.

        ``kind`` is required: a message's role is stamped when the row is made,
        never worked out later from ``request_id`` or timing.
        """
        message = Message(
            group_id=group_id,
            request_id=request_id,
            parent_message_id=parent_message_id,
            direction="inbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            workflow_status=workflow_status,
            **build_message_role(kind=kind, member_id=member_id),
        )
        db.add(message)
        db.flush()
        self._touch_request(db, request_id)
        return message

    def create_outbound(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID | None,
        kind: MessageKind,
        author_member_id: UUID | None = None,
        request_id: int | None = None,
        from_phone_number: str,
        to_phone_number: str,
        body: str,
        provider_message_id: str | None = None,
        parent_message_id: UUID | None = None,
        workflow_status: str = MessageWorkflowStatus.SENT.value,
    ) -> Message:
        """Insert an outbound message.

        ``member_id`` is the recipient. ``author_member_id`` is whoever wrote
        it, and must be NULL for a fan-out copy, which the system generates
        from a body someone else already wrote.
        """
        message = Message(
            group_id=group_id,
            request_id=request_id,
            parent_message_id=parent_message_id,
            direction="outbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            workflow_status=workflow_status,
            **build_message_role(
                kind=kind,
                member_id=member_id,
                author_member_id=author_member_id,
            ),
        )
        db.add(message)
        db.flush()
        self._touch_request(db, request_id)
        return message

    @staticmethod
    def _touch_request(db: Session, request_id: int | None) -> None:
        """Record that the request just saw activity.

        Here rather than in the services because both message constructors are
        the only way a row enters a request, which makes
        ``requests.last_activity_at == max(messages.created_at)`` true by
        construction. The alternative -- each service calling a ``touch`` after
        creating a message -- is four call sites today and silently wrong the
        first time a fifth message path is added.

        ``func.now()`` is transaction time in Postgres, the same clock that
        fills ``messages.created_at``, so the two agree exactly instead of
        differing by however long the flush took.
        """
        if request_id is None:
            return
        db.query(Requests).filter(Requests.id == request_id).update(
            {"last_activity_at": func.now()},
            # The in-session Requests object may keep a stale value until it is
            # next loaded. Nothing reads it inside the same unit of work, and
            # leaving it alone avoids a SELECT on every message insert.
            synchronize_session=False,
        )

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

    def record_routing_policy(
        self,
        db: Session,
        message: Message,
        *,
        routing_policy: str,
    ) -> Message:
        """Snapshot the policy in force when this request was handled.

        Changing the group's policy afterwards must not rewrite why this
        message was handled the way it was. ``kind`` is deliberately not
        touched here: it is stamped at creation and never revised.
        """
        message.routing_policy = routing_policy
        db.add(message)
        db.flush()
        return message

    def apply_approval(
        self,
        db: Session,
        message: Message,
        *,
        routed_recipient_ids: list[UUID],
        workflow_status: str = MessageWorkflowStatus.APPROVED.value,
    ) -> Message:
        """A moderator chose these recipients."""
        return self._apply_routing_decision(
            db,
            message,
            routed_recipient_ids=routed_recipient_ids,
            workflow_status=workflow_status,
        )

    def apply_routing_authorization(
        self,
        db: Session,
        message: Message,
        *,
        routed_recipient_ids: list[UUID],
    ) -> Message:
        """A group policy authorized these recipients — no moderator acted.

        Same machinery as ``apply_approval``, deliberately different status, so
        the stored row never implies a human reviewed this message.
        """
        return self._apply_routing_decision(
            db,
            message,
            routed_recipient_ids=routed_recipient_ids,
            workflow_status=MessageWorkflowStatus.AUTO_AUTHORIZED.value,
        )

    def _apply_routing_decision(
        self,
        db: Session,
        message: Message,
        *,
        routed_recipient_ids: list[UUID],
        workflow_status: str,
    ) -> Message:
        message.routed_recipient_ids = routed_recipient_ids
        message.workflow_status = workflow_status
        db.add(message)
        db.flush()
        return message
