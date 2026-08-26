import os


class Config:
    DATABASE_URL = os.getenv("DATABASE_URL")
    LLM_MODEL_PATH = os.getenv("LLM_MODEL_PATH")
    LLM_EMBEDDING_MODEL_GGUF = os.getenv("LLM_EMBEDDING_MODEL_GGUF")
    SMS_PROVIDER = os.getenv("SMS_PROVIDER", "logging")
    SMS_PROVIDER_URL = os.getenv("SMS_PROVIDER_URL")
