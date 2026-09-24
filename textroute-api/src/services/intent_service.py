"""Discover what a request is, after delivery has already been decided.

The webhook does not call this. A background task does, and the request sweep
retries anything still pending or failed. ``ready`` is committed in the same
transaction as ``request_type``, and only the worker that wins that transition
drains deferred replies.
"""

import logging
from types import SimpleNamespace

from sqlalchemy.orm import Session

from src.core.managers.message_manager import MessageManager
from src.core.managers.request_manager import RequestManager
from src.core.processors.message_processor import MessageProcessor
from src.core.providers.request_analyzer import RequestAnalysis, RequestAnalyzer
from src.domain.intent_status import IntentStatus

logger = logging.getLogger(__name__)


class IntentService:
    def __init__(
        self,
        request_manager: RequestManager | None = None,
        message_manager: MessageManager | None = None,
        request_analyzer: RequestAnalyzer | None = None,
        message_processor: MessageProcessor | None = None,
    ):
        self.request_manager = request_manager or RequestManager()
        self.message_manager = message_manager or MessageManager()
        self.request_analyzer = request_analyzer or RequestAnalyzer()
        self.message_processor = message_processor or MessageProcessor()

    def discover(self, db: Session, request_id: int) -> str:
        """Return ``ready``, ``failed``, or ``skipped``.

        Analysis runs before any status write. The status flip and the
        analysis columns commit together.
        """
        request = self.request_manager.find_by_id(db, request_id)
        if request is None:
            return "skipped"
        status = getattr(request, "intent_status", None)
        if status == IntentStatus.READY.value:
            return "skipped"
        if status not in (IntentStatus.PENDING.value, IntentStatus.FAILED.value, None):
            return "skipped"

        original = None
        original_id = getattr(request, "original_message_id", None)
        if original_id is not None:
            original = self.message_manager.find_by_id(db, original_id)
        body = original.body if original is not None else ""
        logger.info("intent_started", extra={"request_id": request_id})

        try:
            keyword = self.message_processor.process(
                message_body=body,
                sender_id=request.requester_id,
                candidates=[],
            )
            analysis = self.request_analyzer.analyze(
                body,
                fallback=RequestAnalysis(
                    request_type=keyword.intent,
                    summary=(body or "")[:140],
                    extracted_filters=keyword.constraints or {},
                    confidence=keyword.confidence,
                    notes="keyword_fallback",
                ),
            )
        except Exception:
            logger.exception("intent_failed", extra={"request_id": request_id})
            self.request_manager.mark_intent_failed(db, request_id)
            db.commit()
            return "failed"

        self.request_manager.apply_analysis(
            db,
            request,
            request_type=analysis.request_type,
            extracted_filters=analysis.extracted_filters,
            summary=analysis.summary,
            embedding=analysis.embedding,
            model_name=analysis.model_name,
            confidence=analysis.confidence,
        )
        won = self.request_manager.claim_intent_ready(db, request_id)
        if not won:
            db.rollback()
            logger.info("intent_claim_lost", extra={"request_id": request_id})
            return "skipped"

        claimed = self.message_manager.claim_deferred_replies(db, request_id)
        db.commit()
        logger.info(
            "intent_ready",
            extra={
                "request_id": request_id,
                "request_type": analysis.request_type,
                "deferred_reply_count": len(claimed),
            },
        )
        for message in claimed:
            logger.info(
                "deferred_reply_released",
                extra={
                    "request_id": request_id,
                    "message_id": str(message.id),
                    "parent_message_id": (
                        str(message.parent_message_id)
                        if message.parent_message_id
                        else None
                    ),
                },
            )
            self._record_claimed_reply(db, request, message)
        return "ready"

    def discover_outstanding(self, db: Session) -> int:
        """Retry every pending or failed request. One failure does not stop the rest."""
        done = 0
        for request_id in self.request_manager.list_ids_for_intent_discovery(db):
            try:
                if self.discover(db, request_id) == "ready":
                    done += 1
            except Exception:
                db.rollback()
                logger.exception("intent_retry_failed", extra={"request_id": request_id})
        return done

    def _record_claimed_reply(self, db: Session, request, message) -> None:
        """The same record path the webhook uses once intent is ready.

        The claim already flipped the row off ``reply_deferred``, so a webhook
        that also tries to record this reply will not take it again.
        """
        from src.services.inbound_message_service import InboundMessageService

        group = getattr(request, "group", None) or SimpleNamespace(id=request.group_id)
        member = SimpleNamespace(id=message.member_id)
        InboundMessageService(
            message_manager=self.message_manager,
            request_manager=self.request_manager,
        )._handle_member_reply(
            db, message=message, group=group, member=member, request=request
        )


def discover_intent(request_id: int) -> None:
    """Entry point for FastAPI BackgroundTasks. Owns its own session."""
    from src.db.db import SessionLocal

    db = SessionLocal()
    try:
        IntentService().discover(db, request_id)
    except Exception:
        db.rollback()
        logger.exception("intent_failed", extra={"request_id": request_id})
    finally:
        db.close()
