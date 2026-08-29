import os
from datetime import timedelta


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    # Echo SQL and bound parameters. Development aid only; see db/db.py.
    SQL_ECHO = _env_bool("SQL_ECHO", False)
    LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH")
    LLM_EMBEDDING_MODEL_GGUF = os.getenv("LLM_EMBEDDING_MODEL_GGUF")

    # Request analysis. Off by default so a checkout with no Ollama running
    # still handles inbound SMS -- the keyword fallback takes over.
    REQUEST_ANALYSIS_ENABLED = _env_bool("REQUEST_ANALYSIS_ENABLED", False)
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2")
    # Must emit 1024 dimensions to match requests.embedding and its ivfflat
    # index. Changing the model means a migration, not just an env var.
    OLLAMA_EMBEDDING_MODEL = os.getenv(
        "OLLAMA_EMBEDDING_MODEL",
        "qwen3-embedding:0.6b",
    )
    REQUEST_EMBEDDING_DIMENSIONS = int(
        os.getenv("REQUEST_EMBEDDING_DIMENSIONS", "1024")
    )
    # Two bounds on how long a request stays open, both closing it as 'expired'.
    #
    # Inactivity is the normal one: a conversation that has gone quiet for two
    # hours is over, and leaving it open would capture the next unrelated SMS as
    # a reply to it. Expiry is the safety limit for a request that keeps seeing
    # activity but never resolves. Neither has any effect unless the sweep runs;
    # see scripts/sweep_requests.py.
    REQUEST_INACTIVITY_AFTER = timedelta(
        hours=int(os.getenv("REQUEST_INACTIVITY_AFTER_HOURS", "2"))
    )
    REQUEST_EXPIRES_AFTER = timedelta(
        hours=int(os.getenv("REQUEST_EXPIRES_AFTER_HOURS", "72"))
    )

    SMS_PROVIDER = os.getenv("SMS_PROVIDER", "logging")
    SMS_PROVIDER_URL = os.getenv("SMS_PROVIDER_URL")

    # Shared secret for inbound provider webhooks. Unset means the webhook
    # refuses every request; see api/dependencies.verify_webhook_secret.
    WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

    AUTH_SECRET = os.getenv("AUTH_SECRET")
    AUTH_CHALLENGE_TTL_SECONDS = int(os.getenv("AUTH_CHALLENGE_TTL_SECONDS", "600"))
    AUTH_SESSION_TTL_SECONDS = int(os.getenv("AUTH_SESSION_TTL_SECONDS", "28800"))
    AUTH_MAX_ATTEMPTS = int(os.getenv("AUTH_MAX_ATTEMPTS", "5"))
    AUTH_EXPOSE_DEVELOPMENT_CODE = _env_bool(
        "AUTH_EXPOSE_DEVELOPMENT_CODE",
        False,
    )
    AUTH_COOKIE_SECURE = _env_bool("AUTH_COOKIE_SECURE", True)
    AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "textroute_session")
    MODERATOR_WEB_ORIGIN = os.getenv(
        "MODERATOR_WEB_ORIGIN",
        "http://localhost:5174",
    )
    CORS_ALLOWED_ORIGINS = _env_list(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5174,http://localhost:5173",
    )
