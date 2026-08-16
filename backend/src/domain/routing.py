from pathlib import Path
import yaml
from src.schemas.registry import SCHEMA_REGISTRY

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config"


def validate_intents(canonical_intents, aliases):
    for alias, target in aliases.items():
        if target not in canonical_intents:
            raise ValueError(f"Alias '{alias}' points to unknown intent '{target}'")


def load_intent_config():
    # Load canonical intents
    with open(CONFIG_PATH / "intents.yaml", "r") as f:
        intent_config = yaml.safe_load(f)

    # Load aliases
    with open(CONFIG_PATH / "intent_aliases.yaml") as f:
        alias_config = yaml.safe_load(f)

    # Map canonical intent names to schema classes
    intent_schema_map = {
        k: SCHEMA_REGISTRY[v["schema"]]
        for k, v in intent_config["canonical_intents"].items()
    }

    # Validate that all aliases point to valid canonical intents
    validate_intents(intent_config["canonical_intents"], alias_config["aliases"])

    # Keep aliases dictionary for instruction building
    intent_aliases = alias_config["aliases"]

    return intent_schema_map, intent_aliases


# Load at module level
INTENT_SCHEMA_MAP, INTENT_ALIASES = load_intent_config()


# a startup validation check so schema names and configurations match.
def validate_intents(canonical_intents, aliases):
    for alias, target in aliases.items():
        if target not in canonical_intents:
            raise ValueError(f"Alias '{alias}' points to unknown intent '{target}'")
