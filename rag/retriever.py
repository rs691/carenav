"""
rag/retriever.py
────────────────
Hybrid retrieval for CareNav agents.

Strategy:
  1. Embed the query with the configured provider (OpenAI or Ollama)
  2. Dense vector search in the tenant's Qdrant collection
  3. Filter by doc_type if specified
  4. Staleness check — deprioritize chunks from docs older than 90 days
  5. Return top-k chunks with metadata
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

from core.llm import embed_query
from core.settings import settings
from core.tenant import get_tenant

log = structlog.get_logger()

STALENESS_THRESHOLD_DAYS = 90

_qdrant: QdrantClient | None = None


def _get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
        )
    return _qdrant


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
    """
    tenant = get_tenant(tenant_id)
    collection = tenant.rag_namespace

    try:
        query_vector = await embed_query(query)
    except Exception as e:
        log.error("embedding_failed", error=str(e), tenant_id=tenant_id)
        return []

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

    try:
        qdrant = _get_qdrant()
        response = qdrant.query_points(
            collection_name=collection,
            query=query_vector,
            using="dense",
            query_filter=query_filter,
            limit=top_k,
            with_payload=True,
        )
        results = response.points
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
