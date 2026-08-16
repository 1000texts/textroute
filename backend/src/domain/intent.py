# domain/intent.py
from pydantic import BaseModel, field_validator

from src.domain.routing import INTENT_SCHEMA_MAP


class Intent(BaseModel):
    intent: str

    @field_validator("intent")
    def validate_intent(cls, v):
        allowed = set(INTENT_SCHEMA_MAP.keys())
        if v not in allowed:
            raise ValueError(f"Unknown intent: {v}")
        return v
