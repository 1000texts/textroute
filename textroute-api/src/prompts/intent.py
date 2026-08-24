from collections.abc import Mapping


def build_intent_instruction(
    user_text: str,
    canonical_intents: Mapping[str, object],
    aliases: Mapping[str, str],
    instructions: Mapping[str, str],
) -> str:
    canonical_to_aliases = {intent: [] for intent in canonical_intents}
    for alias, canonical in aliases.items():
        canonical_to_aliases[canonical].append(alias)

    intent_lines = [
        f"- {canonical}: {', '.join(intent_aliases) or '(no aliases)'}"
        for canonical, intent_aliases in canonical_to_aliases.items()
    ]

    return "\n".join(
        [
            instructions["intro"],
            *intent_lines,
            instructions["constraint"],
            'Return JSON in this format: { "intent": "<canonical_intent>" }',
            f'User message: "{user_text}"',
        ]
    )
