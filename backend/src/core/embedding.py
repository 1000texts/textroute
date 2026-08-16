from src.config.config import Config
from llama_cpp import Llama
import os

MODEL_PATH = os.path.abspath(
    os.path.join(
        Config.LLM_MODEL_PATH,
        Config.LLM_EMBEDDING_MODEL_GGUF,
    )
)

if not os.path.exists(MODEL_PATH):
    raise RuntimeError(f"LLM model not found at: {MODEL_PATH}")

llm = Llama(
    model_path=MODEL_PATH,
    embedding=True,
    n_ctx=2048,
)


def get_dense_vector():
    print("To do create this function")
