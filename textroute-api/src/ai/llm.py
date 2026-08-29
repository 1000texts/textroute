from langchain_ollama import ChatOllama, OllamaEmbeddings

from src.config.config import Config

# temperature=0: extraction should be reproducible. The same SMS analyzed twice
# must not produce two different sets of filters.
LLM = ChatOllama(
    model=Config.OLLAMA_MODEL,
    temperature=0,
    base_url=Config.OLLAMA_BASE_URL,
)

EMBEDDINGS = OllamaEmbeddings(
    model=Config.OLLAMA_EMBEDDING_MODEL,
    base_url=Config.OLLAMA_BASE_URL,
)

# Swapping providers is a one-line change here:
# from langchain_openai import ChatOpenAI
# LLM = ChatOpenAI(model_name="gpt-4.1", temperature=0)
