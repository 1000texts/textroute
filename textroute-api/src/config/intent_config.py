from dataclasses import dataclass
from typing import Collection

from src.config.yaml_loader import load_yaml


@dataclass(frozen=True)
class IntentConfig:
    schema_names: dict[str, str]
    aliases: dict[str, str]


def load_intent_config(
    valid_schema_names: Collection[str] | None = None,
) -> IntentConfig:
    intent_data = load_yaml("intents.yaml")
    alias_data = load_yaml("intent_aliases.yaml")

    canonical_intents = intent_data.get("canonical_intents")
    aliases = alias_data.get("aliases")
    if not isinstance(canonical_intents, dict) or not isinstance(aliases, dict):
        raise ValueError(
            "Intent config requires 'canonical_intents' and 'aliases' mappings"
        )
    if not all(
        isinstance(alias, str) and isinstance(target, str)
        for alias, target in aliases.items()
    ):
        raise ValueError("Every intent alias and target must be text")

    schema_names = {
        intent: details["schema"]
        for intent, details in canonical_intents.items()
        if isinstance(details, dict) and isinstance(details.get("schema"), str)
    }
    if len(schema_names) != len(canonical_intents):
        raise ValueError("Every canonical intent must define a schema name")

    unknown_targets = {
        target for target in aliases.values() if target not in canonical_intents
    }
    if unknown_targets:
        raise ValueError(
            f"Aliases reference unknown intents: {sorted(unknown_targets)}"
        )

    if valid_schema_names is not None:
        unknown_schemas = set(schema_names.values()) - set(valid_schema_names)
        if unknown_schemas:
            raise ValueError(
                f"Intents reference unknown schemas: {sorted(unknown_schemas)}"
            )

    return IntentConfig(schema_names=schema_names, aliases=aliases)
