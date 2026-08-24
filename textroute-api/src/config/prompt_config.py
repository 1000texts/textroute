from src.config.yaml_loader import load_yaml


def load_intent_instructions() -> dict[str, str]:
    data = load_yaml("instructions_intent.yaml")
    instructions = data.get("instructions")
    if not isinstance(instructions, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in instructions.items()
    ):
        raise ValueError("'instructions_intent.yaml' requires an instructions mapping")
    required_keys = {"intro", "constraint"}
    missing_keys = required_keys - instructions.keys()
    if missing_keys:
        raise ValueError(
            f"Intent instructions are missing keys: {sorted(missing_keys)}"
        )
    return instructions


def load_capture_system_prompt() -> str:
    data = load_yaml("instructions_capture_member_basic.yaml")
    system_prompt = data.get("system_prompt")
    if not isinstance(system_prompt, str):
        raise ValueError(
            "'instructions_capture_member_basic.yaml' requires system_prompt text"
        )
    return system_prompt
