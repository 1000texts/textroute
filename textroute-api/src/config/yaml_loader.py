from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_yaml(filename: str) -> dict[str, Any]:
    path = CONFIG_DIR / filename
    with path.open(encoding="utf-8") as config_file:
        data = yaml.safe_load(config_file)

    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")

    return data
