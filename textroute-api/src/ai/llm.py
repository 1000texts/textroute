import os

from langchain_ollama import ChatOllama

# Reuse LLMs
# LLM = ChatOllama(model="mistral", temperature=0)
# LLM = ChatOllama(model="llama3.1", temperature=0)
LLM = ChatOllama(model="qwen2", temperature=0)
LLM = ChatOllama(
    model="qwen2",
    temperature=0,
    base_url=os.getenv(
        "OLLAMA_BASE_URL",
        "http://localhost:11434",
    ),
)
# from langchain_openai import ChatOpenAI
# LLM = ChatOpenAI(model_name="gpt-4.1", temperature=0)
