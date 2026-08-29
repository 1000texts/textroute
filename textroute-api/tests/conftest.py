"""Test bootstrap.

The tests are unit tests and never open a connection, but importing anything
under ``src.api`` pulls in ``src.db.db``, which refuses to import without a
``DATABASE_URL``. Load the project's ``.env`` so ``pytest`` works from a bare
shell, and fall back to a placeholder so a contributor who has not written one
yet can still run the suite.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]

for candidate in (_REPO_ROOT / "textroute-api" / ".env", _REPO_ROOT / ".env"):
    if candidate.exists():
        load_dotenv(candidate, override=False)

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://textroute:textroute@localhost:5432/textroute_test",
)
