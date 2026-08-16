from pathlib import Path
import yaml
from functools import lru_cache

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config"

# ---------- Cache YAML loads for performance ----------


@lru_cache(maxsize=1)
def _load_instructions_yaml():
    """Load instructions.yaml once per process."""
    with open(f"{CONFIG_PATH}/instructions.yaml") as f:
        return yaml.safe_load(f)["instructions"]


# ---------- Schema / Intent instruction helpers ----------


def schema_instruction(schema_cls):
    """Generate instruction for a specific schema class."""
    return f"Extract a structured {schema_cls.__name__} from the text below."


def intent_instruction(intent_schema_map):
    """
    Generate LLM instruction string for intent detection.
    Dynamically includes all canonical intents.
    """
    instructions = _load_instructions_yaml()
    intents_list = ", ".join(f"'{intent}'" for intent in intent_schema_map)
    instruction_str = (
        f"{instructions['intent1']}{intents_list}"
        f"{instructions['intent2']}\n\nInput: {{text}}"
    )
    return instruction_str
