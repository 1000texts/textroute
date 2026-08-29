# domain/intent.py
from pydantic import BaseModel, Field, field_validator

from src.domain.routing import INTENT_SCHEMA_MAP


class Intent(BaseModel):
    """Structured output for intent classification."""

    intent: str
    # Asked for as part of the structured output rather than derived afterwards:
    # only the model knows how sure it was, and a number computed outside it
    # would be a guess dressed up as a measurement.
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("intent")
    def validate_intent(cls, v):
        allowed = set(INTENT_SCHEMA_MAP.keys())
        if v not in allowed:
            raise ValueError(f"Unknown intent: {v}")
        return v
