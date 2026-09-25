"""
rag/retriever.py
────────────────
Hybrid retrieval for CareNav agents.

Strategy:
  1. Embed the query with text-embedding-3-small
  2. Dense vector search in the tenant's Qdrant collection
  3. Filter by doc_type if specified
  4. Staleness check — deprioritize chunks from docs older than 90 days
  5. Return top-k chunks with metadata

Usage in an agent:
    from rag.retriever import retrieve
    chunks = await retrieve(
        query="Is my MRI covered?",
        tenant_id="tenant_bcbs",
        doc_type="benefits",
        top_k=5,
    )
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

import structlog
from openai import AsyncOpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.settings import settings
from core.tenant import get_tenant

log = structlog.get_logger()

STALENESS_THRESHOLD_DAYS = 90

# Module-level clients — initialized once
_qdrant: QdrantClient | None = None
_openai: AsyncOpenAI | None = None


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
        )
    return _qdrant


def _get_openai() -> AsyncOpenAI:
    global _openai
    if _openai is None:
        _openai = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai


async def _embed(text: str) -> list[float]:
    client = _get_openai()
    response = await client.embeddings.create(
        model=settings.openai_embedding_model,
        input=text,
    )
    return response.data[0].embedding


def _is_stale(effective_date_str: str) -> bool:
    """Returns True if the document is older than STALENESS_THRESHOLD_DAYS."""
    if not effective_date_str:
        return False
    try:
        effective = datetime.fromisoformat(effective_date_str.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - effective
        return age.days > STALENESS_THRESHOLD_DAYS
    except ValueError:
        return False


async def retrieve(
    query: str,
    tenant_id: str,
    doc_type: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    Retrieve the top-k most relevant chunks for a query.

    Args:
        query:     Member's question (already PHI-scrubbed by guardrail layer)
        tenant_id: Scopes retrieval to this tenant's collection
        doc_type:  Optional filter — "benefits" | "formulary" | "policy"
        top_k:     Number of chunks to return

    Returns:
        List of chunk dicts with text, metadata, score, and staleness flag.
    """
    tenant = get_tenant(tenant_id)
    collection = tenant.rag_namespace

    # Embed the query
    try:
        query_vector = await _embed(query)
    except Exception as e:
        log.error("embedding_failed", error=str(e), tenant_id=tenant_id)
        return []

    # Build optional doc_type filter
    query_filter = None
    if doc_type:
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="doc_type",
                    match=MatchValue(value=doc_type),
                )
            ]
        )

    # Dense vector search
    try:
        qdrant = _get_qdrant()
        results = qdrant.search(
            collection_name=collection,
            query_vector=("dense", query_vector),
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
    except Exception as e:
        log.error(
            "qdrant_search_failed",
            error=str(e),
            collection=collection,
            tenant_id=tenant_id,
        )
        return []

    chunks = []
    stale_count = 0

    for hit in results:
        payload = hit.payload or {}
        stale = _is_stale(payload.get("effective_date", ""))

        if stale:
            stale_count += 1

        chunks.append({
            "text": payload.get("text", ""),
            "source_doc": payload.get("source_doc_id", ""),
            "section": payload.get("section", ""),
            "doc_type": payload.get("doc_type", ""),
            "effective_date": payload.get("effective_date", ""),
            "chunk_index": payload.get("chunk_index", 0),
            "score": round(hit.score, 4),
            "stale": stale,
        })

    if stale_count > 0:
        log.warning(
            "stale_chunks_returned",
            stale_count=stale_count,
            total=len(chunks),
            tenant_id=tenant_id,
            collection=collection,
        )

    log.info(
        "retrieval_complete",
        tenant_id=tenant_id,
        query_length=len(query),
        chunks_returned=len(chunks),
        stale_chunks=stale_count,
    )

    return chunks