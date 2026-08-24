from datetime import datetime


def build_extraction_messages(now: datetime | None = None):
    current_time = now or datetime.now()
    return [
        (
            "system",
            "You are a helpful assistant specialized in extracting structured data from text.\n"
            "Always output valid JSON strictly following the provided schema.\n"
            "No markdown, no explanations, no extra text.\n"
            "Time handling rules (MANDATORY):\n"
            "   - Do NOT invent dates or times\n"
            "   - Only extract a datetime if the user explicitly provides one\n"
            "   - If no date or time is mentioned, output null for all datetime fields\n"
            "   - Never guess based on holidays, seasons, or context\n"
            "   - The system will set created_at automatically\n"
            f"   - The current timestamp is {current_time}\n",
        ),
        (
            "human",
            "{task}\n"
            "Here are the format instructions:\n{format_instructions}\n\n"
            "Text to process:\n{text}",
        ),
    ]


def build_schema_instruction(schema_cls) -> str:
    return (
        f"Extract a structured {schema_cls.__name__} object from the text below.\n"
        "Rules:\n"
        "1. Use ONLY the fields defined in the schema.\n"
        "2. Output strictly valid JSON. No markdown, explanations, or extra text.\n"
        "3. For all datetime fields, output UTC in ISO 8601 format when explicitly "
        'provided, e.g. "2025-12-21T18:30:00Z".\n'
        "4. If an optional field is absent, omit it or set it to null.\n"
        "5. Nested objects must follow the same rules.\n"
        "6. Ensure Pydantic can parse the JSON without modification.\n\n"
        "Return the structured JSON object for the given text."
    )
