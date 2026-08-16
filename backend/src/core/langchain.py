from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain_ollama import ChatOllama
from src.domain.routing import INTENT_ALIASES, INTENT_SCHEMA_MAP
from src.domain.intent import Intent
from src.schemas.registry import SCHEMA_REGISTRY
import os

# Reuse LLMs
# LLM = ChatOllama(model="mistral", temperature=0)
# LLM = ChatOllama(model="llama3.1", temperature=0)
LLM = ChatOllama(model="qwen2", temperature=0)
LLM = ChatOllama(
    model="qwen2",
    temperature=0,
    base_url=os.getenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434",
    ),
)
# from langchain_openai import ChatOpenAI
# LLM = ChatOpenAI(model_name="gpt-4.1", temperature=0)


def analyze_request_payload(text: str):
    # 0. Determine intent dynamically
    intent = find_intent(text)

    # Validate intent
    chosen_schema = INTENT_SCHEMA_MAP.get(intent, SCHEMA_REGISTRY["GeneralRequest"])

    # 1. Parser for the chosen schema
    parser = PydanticOutputParser(pydantic_object=chosen_schema)

    # 2. Schema-aware prompt
    system_prompt = build_system_instruction()
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


def find_intent(text: str) -> str:
    """
    Determine the canonical intent for the given text using LLM only.
    """
    # Build instruction with canonical intents and aliases
    instruction = build_intent_instruction(text)

    # Use structured output to parse JSON into Intent model
    intent_chain = LLM.with_structured_output(Intent)
    inference = intent_chain.invoke(instruction)

    return inference.intent


###################### Helper functions for building prompts and instructions ######################
def build_system_instruction():
    return [
        (
            "system",
            "You are a helpful assistant specialized in extracting structured data from text.\n"
            "Always output valid JSON strictly following the provided schema.\n"
            "No markdown, no explanations, no extra text.\n"
            "Time handling rules (MANDATORY):\n"
            "   - Do NOT invent dates or times"
            "   - Only extract a datetime if the user explicitly provides one\n"
            "   - If no date or time is mentioned, output null for all datetime fields\n"
            "   - Never guess based on holidays, seasons, or context\n"
            "   - The system will set created_at automatically\n"
            f"  - FYI, the current timestamp is {datetime.now()}\n",
        ),
        (
            "human",
            "{task}\n"
            "Here are the format instructions:\n{format_instructions}\n\n"
            "Text to process:\n{text}",
        ),
    ]


def build_schema_instruction(schema_cls):
    """
    Generate clear, structured instructions for the LLM to extract data
    according to the given Pydantic schema.
    """
    return (
        f"Extract a structured {schema_cls.__name__} object from the text below.\n"
        "Rules:\n"
        "1. Use ONLY the fields defined in the schema.\n"
        "2. Output strictly valid JSON. No markdown, explanations, or extra text.\n"
        "3. For all datetime fields, always output the actual UTC datetime in ISO 8601 format, "
        'e.g. "2025-12-21T18:30:00Z". Never use placeholder text like YYYY-MM-DDTHH:mm:ss.\n'
        "4. If a field is optional and not present, you may omit it or set it to null.\n"
        "5. Nested objects must follow the same rules.\n"
        "6. Ensure JSON can be parsed directly by Pydantic without modification.\n\n"
        "Return the structured JSON object for the given text."
    )


def build_intent_instruction(user_text: str) -> str:
    """
    Construct instruction for the LLM including canonical intents and aliases.
    """
    instruction_lines = [
        "You are an assistant that classifies user requests into canonical intents."
    ]
    instruction_lines.append("Here are the intents and their aliases:")

    # Group aliases by canonical intent
    canonical_to_aliases = {}
    for alias, canonical in INTENT_ALIASES.items():
        canonical_to_aliases.setdefault(canonical, []).append(alias)

    for canonical, aliases in canonical_to_aliases.items():
        aliases_str = ", ".join(aliases)
        instruction_lines.append(f"- {canonical}: {aliases_str}")

    instruction_lines.append(
        "Given a user message, output the canonical intent ONLY.\n"
        'Return JSON in this format: { "intent": "<canonical_intent>" }'
    )

    instruction_lines.append(f'User message: "{user_text}"')

    return "\n".join(instruction_lines)
