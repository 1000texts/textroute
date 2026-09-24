"""Understanding what a request is asking for.

An integration seam, which is why it lives under ``providers``: everything it
touches (Ollama, LangChain, model weights) is outside the process and can be
slow, absent, or wrong. The rest of the application depends on the
``RequestAnalysis`` dataclass, not on LangChain.

The analyzer never decides anything. It describes a request -- type, summary,
filters, embedding -- so a moderator or a future matcher can act on the
description. Recipient selection stays in ``MessageProcessor``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.config.config import Config

logger = logging.getLogger(__name__)


@dataclass
class RequestAnalysis:
    """What the analyzer understood, and how it got there.

    ``model_name`` is None for the keyword fallback, which is how a reader can
    tell a genuine model result from a degraded one.
    """

    request_type: str
    summary: str | None = None
    extracted_filters: dict = field(default_factory=dict)
    embedding: list[float] | None = None
    confidence: float = 0.0
    model_name: str | None = None
    notes: str = ""

    @property
    def used_model(self) -> bool:
        return self.model_name is not None


class RequestAnalyzer:
    """Analyze request text, degrading to keywords rather than failing.

    An SMS that arrives while Ollama is down must still reach a moderator. The
    request is the durable object; its analysis is an enrichment that can be
    recomputed later, so a model failure is logged and downgraded, never raised.
    """

    def __init__(self, *, enabled: bool | None = None):
        self.enabled = Config.REQUEST_ANALYSIS_ENABLED if enabled is None else enabled

    def analyze(self, text: str, *, fallback: RequestAnalysis) -> RequestAnalysis:
        """Describe ``text``, or return ``fallback`` if the model cannot.

        The caller supplies the fallback because it already ran the keyword
        classifier to pick recipients; recomputing it here would be a second
        answer to a question already asked.
        """
        if not self.enabled:
            return fallback

        try:
            analysis = self._analyze_with_model(text)
        except Exception:
            logger.exception("request_analysis_failed")
            fallback.notes = "analysis_failed_keyword_fallback"
            return fallback

        analysis.embedding = self._embed(text)
        return analysis

    def _analyze_with_model(self, text: str) -> RequestAnalysis:
        # Imported lazily: LangChain and Ollama clients are heavy, and a
        # deployment that leaves analysis disabled should not pay to import them
        # or fail at startup if they are missing.
        from src.ai.extraction import analyze_request_payload

        intent, _schema, extracted = analyze_request_payload(text)
        # ``mode="json"`` because these filters are stored in a JSONB column, and
        # every intent schema carries datetime fields (``created_at``, and dates
        # like ``borrow_date`` or ``expires_at``). A Python ``datetime`` reaches
        # the driver unserializable and raises at flush -- after this method has
        # returned, so the degrade-to-keywords guard above cannot catch it, and
        # the inbound SMS is lost rather than downgraded.
        filters = extracted.model_dump(mode="json", exclude_none=True)
        # The schemas default ``created_at`` to now, so it is not extracted from
        # the message at all -- the model never saw it. Keeping it would put a
        # timestamp in the moderator's summary and imply the SMS said something
        # about time. ``requests.created_at`` already records arrival.
        filters.pop("created_at", None)

        return RequestAnalysis(
            request_type=intent.intent,
            summary=self._summarize(intent.intent, filters, text),
            extracted_filters=filters,
            confidence=intent.confidence,
            model_name=Config.OLLAMA_MODEL,
            notes="analyzed",
        )

    def _embed(self, text: str) -> list[float] | None:
        """Embed for future semantic matching; None if unavailable.

        A wrong-width vector is rejected here rather than at the INSERT, because
        the column is fixed-width for ivfflat and a mismatch means the
        configured model does not match the schema -- a deployment problem worth
        naming clearly.
        """
        try:
            from src.ai.llm import EMBEDDINGS

            vector = EMBEDDINGS.embed_query(text)
        except Exception:
            logger.exception("request_embedding_failed")
            return None

        expected = Config.REQUEST_EMBEDDING_DIMENSIONS
        if len(vector) != expected:
            logger.error(
                "request_embedding_wrong_dimension",
                extra={"expected": expected, "actual": len(vector)},
            )
            return None
        return vector

    @staticmethod
    def _summarize(request_type: str, filters: dict, text: str) -> str:
        """A short human-readable line for the moderator's request list.

        Assembled from the extracted fields rather than asking the model for
        prose: it is one more round trip for something the structured output
        already contains, and a generated summary could disagree with the
        filters shown beside it.
        """
        parts = [str(v) for v in filters.values() if isinstance(v, (str, int, float))]
        if not parts:
            return text[:140]
        return f"{request_type.replace('_', ' ')}: {', '.join(parts[:4])}"
