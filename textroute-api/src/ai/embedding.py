from src.config.config import Config
from llama_cpp import Llama
import os

_MODEL_DIR = Config.LLM_MODEL_PATH
_MODEL_FILE = Config.LLM_EMBEDDING_MODEL_GGUF

# Both are unset by default, so say which one is missing rather than joining
# None into a path and failing later with something less obvious.
if not _MODEL_DIR or not _MODEL_FILE:
    raise RuntimeError(
        "Local GGUF embeddings need LLM_MODEL_PATH and "
        "LLM_EMBEDDING_MODEL_GGUF to be set."
    )

MODEL_PATH = os.path.abspath(os.path.join(_MODEL_DIR, _MODEL_FILE))

if not os.path.exists(MODEL_PATH):
    raise RuntimeError(f"LLM model not found at: {MODEL_PATH}")

llm = Llama(
    model_path=MODEL_PATH,
    embedding=True,
    n_ctx=2048,
)


def get_dense_vector(*, user_text: str) -> list[float]:
    """Embed one string with the local GGUF model.

    Keyword-only to match the call in ``filters.py`` and because a bare string
    argument at a call site says nothing about which text is being embedded.
    """
    return llm.embed(user_text)
