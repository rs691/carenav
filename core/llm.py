"""
core/llm.py
───────────
Provider-agnostic chat + embeddings for CareNav.

Providers:
  - openai  — OpenAI API (paid credits)
  - ollama  — local free models via http://127.0.0.1:11434

Set LLM_PROVIDER=ollama in .env to run without OpenAI billing.
"""

from __future__ import annotations

from functools import lru_cache

import httpx
import structlog

from core.settings import settings

log = structlog.get_logger()

# Known embedding sizes used when creating Qdrant collections
EMBEDDING_DIMS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "nomic-embed-text": 768,
    "nomic-embed-text:latest": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
}


def llm_enabled() -> bool:
    """True when a chat/embed backend is configured."""
    provider = settings.llm_provider.lower().strip()
    if provider == "ollama":
        return True
    return bool(settings.openai_api_key)


OLLAMA_SLA_MULTIPLIER = 6


def agent_timeout_seconds(latency_sla_ms: int) -> float:
    """Agent SLAs assume a hosted model; local Ollama gets proportionally more time."""
    seconds = latency_sla_ms / 1000
    if settings.llm_provider.lower().strip() == "ollama":
        return seconds * OLLAMA_SLA_MULTIPLIER
    return seconds


def embedding_dimensions() -> int:
    model = settings.effective_embedding_model
    if model in EMBEDDING_DIMS:
        return EMBEDDING_DIMS[model]
    # Ollama nomic family default
    if "nomic-embed" in model:
        return 768
    if settings.llm_provider.lower() == "ollama":
        return 768
    return 1536


def get_chat_llm(*, temperature: float = 0):
    """Return a LangChain chat model for the configured provider."""
    from langchain_openai import ChatOpenAI

    provider = settings.llm_provider.lower().strip()
    if provider == "ollama":
        return ChatOpenAI(
            model=settings.effective_chat_model,
            temperature=temperature,
            api_key="ollama",
            base_url=settings.ollama_base_url.rstrip("/") + "/v1",
        )
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not set and LLM_PROVIDER is not ollama")
    return ChatOpenAI(
        model=settings.effective_chat_model,
        temperature=temperature,
        api_key=settings.openai_api_key,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Sync batch embeddings for ingest."""
    if not texts:
        return []
    provider = settings.llm_provider.lower().strip()
    if provider == "ollama":
        return _ollama_embed_batch(texts)
    return _openai_embed_batch(texts)


async def embed_query(text: str) -> list[float]:
    """Async single-query embedding for retrieval."""
    provider = settings.llm_provider.lower().strip()
    if provider == "ollama":
        # Ollama HTTP is sync; run in thread to avoid blocking the event loop
        import asyncio

        return await asyncio.to_thread(_ollama_embed_one, text)
    return await _openai_embed_one_async(text)


def _openai_embed_batch(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(
        model=settings.effective_embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def _openai_embed_one_async(text: str) -> list[float]:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.embeddings.create(
        model=settings.effective_embedding_model,
        input=text,
    )
    return response.data[0].embedding


def _ollama_embed_one(text: str) -> list[float]:
    url = settings.ollama_base_url.rstrip("/") + "/api/embeddings"
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(
            url,
            json={"model": settings.effective_embedding_model, "prompt": text},
        )
        resp.raise_for_status()
        data = resp.json()
    embedding = data.get("embedding")
    if not embedding:
        raise RuntimeError(f"Ollama embedding response missing 'embedding': {data}")
    return embedding


def _ollama_embed_batch(texts: list[str]) -> list[list[float]]:
    # Ollama embeddings API is one prompt per call
    out: list[list[float]] = []
    for i, text in enumerate(texts):
        if i and i % 10 == 0:
            log.info("ollama_embed_progress", done=i, total=len(texts))
        out.append(_ollama_embed_one(text))
    return out


@lru_cache(maxsize=1)
def probe_ollama() -> bool:
    try:
        url = settings.ollama_base_url.rstrip("/") + "/api/tags"
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            resp.raise_for_status()
        return True
    except Exception as e:
        log.warning("ollama_unreachable", error=str(e), url=settings.ollama_base_url)
        return False
