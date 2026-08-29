from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import ChatPromptTemplate

from src.ai.intent import find_intent
from src.ai.llm import LLM
from src.domain.routing import INTENT_SCHEMA_MAP
from src.prompts.extraction import (
    build_extraction_messages,
    build_schema_instruction,
)
from src.schemas.registry import SCHEMA_REGISTRY


def analyze_request_payload(text: str):
    """Classify then extract, returning ``(intent, schema, extracted)``.

    ``intent`` is the full ``Intent`` object, so its confidence survives the
    round trip to the caller.
    """
    # 0. Determine intent dynamically
    intent = find_intent(text)

    # Validate intent
    chosen_schema = INTENT_SCHEMA_MAP.get(
        intent.intent, SCHEMA_REGISTRY["GeneralRequest"]
    )

    # 1. Parser for the chosen schema
    parser = PydanticOutputParser(pydantic_object=chosen_schema)

    # 2. Schema-aware prompt
    system_prompt = build_extraction_messages()
    prompt = ChatPromptTemplate.from_messages(system_prompt)

    # 3. Chain: prompt -> LLM -> parser
    chain = prompt | LLM | parser

    # 4. Run
    result = chain.invoke(
        {
            "task": build_schema_instruction(
                chosen_schema
            ),  # generate schema-specific instructions
            "text": text,
            "format_instructions": parser.get_format_instructions(),  # from PydanticOutputParser
        }
    )

    return intent, chosen_schema, result  # result is already a Pydantic object,
