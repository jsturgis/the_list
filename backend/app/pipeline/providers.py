"""LLM provider abstraction — swap Haiku for a local Ollama model via config."""
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from app.config import settings


def get_enrichment_llm() -> BaseChatModel:
    # To switch to a local Ollama model, replace with ChatOllama and set
    # OLLAMA_ENRICHMENT_MODEL in .env — no other code changes needed.
    return ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=settings.anthropic_api_key,
        max_tokens=1024,
    )
