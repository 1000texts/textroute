from src.config.intent_config import load_intent_config
from src.schemas.registry import SCHEMA_REGISTRY

_intent_config = load_intent_config(SCHEMA_REGISTRY.keys())

INTENT_SCHEMA_MAP = {
    intent: SCHEMA_REGISTRY[schema_name]
    for intent, schema_name in _intent_config.schema_names.items()
}
INTENT_ALIASES = _intent_config.aliases
