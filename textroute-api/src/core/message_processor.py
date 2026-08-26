from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from src.models import Message


@dataclass
class ProcessingResult:
    """Outcome of inbound message processing.

    Expand later with intent, matched members, and route lists.
    """

    response_body: str | None = None
    route_member_ids: list = field(default_factory=list)
    notes: str | None = None


class MessageProcessor:
    """Interpret inbound SMS and decide what should happen next.

    Extension point for the AI stack (``src.ai``, ``src.domain``):
    classify intent → extract filters → match members → set
    ``response_body`` / ``route_member_ids``.

    Current implementation is a no-op so the inbound pipeline can
    persist messages without depending on LLM wiring.
    """

    def process(
        self,
        db: Session,
        message: Message,
    ) -> ProcessingResult:
        return ProcessingResult(
            response_body=None,
            route_member_ids=[],
            notes="processor_not_implemented",
        )
