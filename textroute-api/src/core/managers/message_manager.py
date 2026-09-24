from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from src.domain.association import AWAITING_CHOICE
from src.domain.intent_status import REPLY_CLAIMED, REPLY_DEFERRED
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

    def list_conversation(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
        after_created_at: datetime | None = None,
        after_id: UUID | None = None,
        limit: int = 200,
    ) -> list[Message]:
        """Everything one member and one group have said to each other.

        ``member_id`` is the member a row is *about* -- the sender inbound, the
        recipient outbound -- so this pair of columns is the whole conversation,
        in both directions, with no phone-number matching needed.

        Deliberately unfiltered by ``kind``. A fan-out copy, a moderator
        clarification and a confirmation all reach the member's handset, so all
        of them belong here; deciding which of them *mattered* is the job of the
        request, not of the phone.

        Returned oldest first, the order a conversation is read in.
        """
        query = db.query(Message).filter(
            Message.group_id == group_id,
            Message.member_id == member_id,
        )

        if after_created_at is None or after_id is None:
            # No cursor means the first load, which wants the newest page and
            # then reads forwards -- hence the descending fetch and reverse. A
            # plain ascending limit would pin the view to the oldest messages
            # and never reach the recent ones.
            newest_first = (
                query.order_by(Message.created_at.desc(), Message.id.desc())
                .limit(limit)
                .all()
            )
            return list(reversed(newest_first))

        # A keyset cursor on ``created_at`` alone is not a continuation point: a
        # fan-out writes its copies in one transaction, where ``func.now()`` is
        # transaction time, so siblings share a timestamp exactly. ``>`` would
        # then skip every sibling but one and never come back for them. The
        # primary key breaks the tie and makes the cursor total.
        #
        # ``id`` is a random UUID, so it orders tied rows arbitrarily rather than
        # by arrival. That is enough: paging is exact as long as the cursor and
        # the ORDER BY agree, and rows tied to the microsecond were written in
        # one transaction, so no arrival order exists to preserve.
        return (
            query.filter(
                or_(
                    Message.created_at > after_created_at,
                    and_(
                        Message.created_at == after_created_at,
                        Message.id > after_id,
                    ),
                )
            )
            # Must match the cursor's own comparison, or rows could be ordered
            # one way and paged another.
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
            .all()
        )

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

    def create_pending_choice(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
        from_phone_number: str,
        to_phone_number: str,
        body: str,
        provider_message_id: str | None,
        choices: dict,
    ) -> Message:
        """An inbound text whose kind is not stamped yet.

        ``kind`` stays null until the sender's letter says which request it
        belongs to. ``request_id`` stays null for the same reason.
        """
        message = Message(
            group_id=group_id,
            member_id=member_id,
            author_member_id=member_id,
            direction="inbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            workflow_status=MessageWorkflowStatus.RECEIVED.value,
            processing_notes=AWAITING_CHOICE,
            constraints={"clarification": choices},
        )
        db.add(message)
        db.flush()
        return message

    def find_pending_clarification(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
    ) -> Message | None:
        """The sender's unanswered letter question, if they have one."""
        return (
            db.query(Message)
            .filter(
                Message.group_id == group_id,
                Message.member_id == member_id,
                Message.direction == "inbound",
                Message.kind.is_(None),
                Message.processing_notes == AWAITING_CHOICE,
            )
            .order_by(Message.created_at.desc())
            .first()
        )

    def record_choice_text(
        self,
        db: Session,
        *,
        group_id: UUID,
        member_id: UUID,
        from_phone_number: str,
        to_phone_number: str,
        body: str,
        provider_message_id: str | None,
        note: str,
    ) -> Message:
        """Persist the letter SMS itself. It is not a request and not weighed."""
        message = Message(
            group_id=group_id,
            member_id=member_id,
            author_member_id=member_id,
            direction="inbound",
            from_phone_number=from_phone_number,
            to_phone_number=to_phone_number,
            body=body,
            provider_message_id=provider_message_id,
            workflow_status=MessageWorkflowStatus.RECEIVED.value,
            processing_notes=note,
        )
        db.add(message)
        db.flush()
        return message

    def attach_held_message(
        self,
        db: Session,
        message: Message,
        *,
        kind: MessageKind,
        member_id: UUID,
        request_id: int,
        parent_message_id: UUID | None,
    ) -> Message:
        """Stamp a held inbound once the sender's letter has chosen its request."""
        role = build_message_role(kind=kind, member_id=member_id)
        message.kind = role["kind"]
        message.sender_role = role["sender_role"]
        message.member_id = role["member_id"]
        message.author_member_id = role["author_member_id"]
        message.request_id = request_id
        message.parent_message_id = parent_message_id
        message.processing_notes = "choice_applied"
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

    def claim_deferred_replies(self, db: Session, request_id: int) -> list[Message]:
        """Flip each deferred reply to recorded. A lost race returns nothing for that row."""
        waiting = (
            db.query(Message)
            .filter(
                Message.request_id == request_id,
                Message.processing_notes == REPLY_DEFERRED,
            )
            .all()
        )
        claimed: list[Message] = []
        for message in waiting:
            updated = (
                db.query(Message)
                .filter(
                    Message.id == message.id,
                    Message.processing_notes == REPLY_DEFERRED,
                )
                .update(
                    {"processing_notes": REPLY_CLAIMED},
                    synchronize_session=False,
                )
            )
            if updated == 1:
                message.processing_notes = REPLY_CLAIMED
                claimed.append(message)
        return claimed

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
