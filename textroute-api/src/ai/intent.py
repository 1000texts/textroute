from src.ai.llm import LLM
from src.config.prompt_config import load_intent_instructions
from src.domain.intent import Intent
from src.domain.routing import INTENT_ALIASES, INTENT_SCHEMA_MAP
from src.prompts.intent import build_intent_instruction


def find_intent(text: str) -> Intent:
    """Classify text into a canonical intent, with the model's own confidence.

    Returns the whole ``Intent`` rather than just the string, because the
    confidence has to travel with the classification it describes.
    """
    # Build instruction with canonical intents and aliases
    instruction = build_intent_instruction(
        text,
        canonical_intents=INTENT_SCHEMA_MAP,
        aliases=INTENT_ALIASES,
        instructions=load_intent_instructions(),
    )

    # Use structured output to parse JSON into Intent model
    intent_chain = LLM.with_structured_output(Intent)
    return intent_chain.invoke(instruction)
