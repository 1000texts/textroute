from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from src.models import Member


@dataclass(frozen=True)
class MemberContext:
    """Processor-facing member snapshot (no ORM session required)."""

    id: UUID
    phone_number: str
    name: str | None = None
    role: str = "member"


@dataclass
class ProcessingResult:
    """AI / heuristic recommendation — not a delivery decision.

    The application (moderator + MessagingService) decides what happens next.
    """

    intent: str
    constraints: dict = field(default_factory=dict)
    suggested_recipient_ids: list[UUID] = field(default_factory=list)
    confidence: float = 0.0
    notes: str | None = None
    # Per-recipient short rationale for the moderator UI (id → reason)
    suggestion_reasons: dict[UUID, str] = field(default_factory=dict)


class MessageProcessor:
    """Pure application/domain boundary: Message + context → ProcessingResult.

    Does not send SMS, commit transactions, or mutate memberships.
    """

    def process(
        self,
        *,
        message_body: str,
        sender_id: UUID,
        candidates: list[MemberContext],
    ) -> ProcessingResult:
        intent, confidence, constraints = self._classify(message_body)
        recipients = [c for c in candidates if c.id != sender_id]
        reasons = {
            c.id: self._reason_for(c, intent)
            for c in recipients
        }
        return ProcessingResult(
            intent=intent,
            constraints=constraints,
            suggested_recipient_ids=[c.id for c in recipients],
            confidence=confidence,
            notes="heuristic_v1_suggest_active_members",
            suggestion_reasons=reasons,
        )

    def _classify(self, body: str) -> tuple[str, float, dict]:
        text = body.lower()
        constraints: dict = {}

        if any(
            token in text
            for token in ("borrow", "lend", "can i use", "does anyone have")
        ):
            # crude object guess: words after "have a/an" or "borrow a/an"
            obj = self._extract_after(text, ("have a ", "have an ", "borrow a ", "borrow an "))
            if obj:
                constraints["object"] = obj
            if "weekend" in text:
                constraints["time_constraint"] = "this weekend"
            elif "today" in text:
                constraints["time_constraint"] = "today"
            elif "tomorrow" in text:
                constraints["time_constraint"] = "tomorrow"
            return "request_borrow", 0.45, constraints

        if any(token in text for token in ("i can help", "i have a", "i've got", "offering")):
            return "offer_service", 0.4, constraints

        if any(token in text for token in ("fyi", "announcement", "heads up", "reminder")):
            return "announcement", 0.4, constraints

        if "?" in body:
            return "general", 0.3, constraints

        return "general", 0.25, constraints

    @staticmethod
    def _extract_after(text: str, markers: tuple[str, ...]) -> str | None:
        for marker in markers:
            idx = text.find(marker)
            if idx >= 0:
                rest = text[idx + len(marker) :].strip()
                # take up to ~4 words / punctuation
                words: list[str] = []
                for raw in rest.split():
                    cleaned = raw.strip(".,!?;:\"'")
                    if not cleaned:
                        break
                    words.append(cleaned)
                    if len(words) >= 4:
                        break
                if words:
                    return " ".join(words)
        return None

    @staticmethod
    def _reason_for(candidate: MemberContext, intent: str) -> str:
        label = candidate.name or candidate.phone_number
        if intent == "request_borrow":
            return f"{label} — active group member (no profile match yet)"
        return f"{label} — active group member"


def member_context_from_orm(member: Member, *, role: str = "member") -> MemberContext:
    return MemberContext(
        id=member.id,
        phone_number=member.phone_number,
        name=member.name,
        role=role,
    )
