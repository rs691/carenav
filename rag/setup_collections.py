"""
rag/setup_collections.py
────────────────────────
Creates all tenant Qdrant collections with the correct vector config.
Run once after you have your Qdrant keys, and again whenever you add a new tenant.

Usage (from project root with venv active):
    python rag/setup_collections.py

Safe to re-run — skips collections that already exist.
"""

import asyncio
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    HnswConfigDiff,
    OptimizersConfigDiff,
)
from core.tenant import TENANT_REGISTRY
from core.settings import settings

# ── Config ────────────────────────────────────────────────────────────────────

# Must match your embedding model output dimension.
# text-embedding-3-small → 1536
# text-embedding-3-large → 3072
# text-embedding-ada-002 → 1536
VECTOR_SIZE = 1536

# Hybrid search: store both dense vectors and sparse (BM25) vectors.
# Sparse vectors power the keyword side of hybrid search.
# We use named vectors so both live in the same collection.
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"


def get_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
    )


def collection_exists(client: QdrantClient, name: str) -> bool:
    existing = [c.name for c in client.get_collections().collections]
    return name in existing


def create_collection(client: QdrantClient, name: str) -> None:
    """
    Create a collection with:
    - Dense vectors for semantic similarity search
    - HNSW index tuned for recall vs speed balance
    - Payload indexing on fields we filter by (tenant_id, doc_type, effective_date)
    """
    client.create_collection(
        collection_name=name,
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        },
        # HNSW tuning:
        # m=16 — connections per node, higher = better recall, more memory
        # ef_construct=100 — build-time search width, higher = better index quality
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=100,
        ),
        # Optimizer: indexing_threshold controls when HNSW kicks in.
        # 0 = always use HNSW (good for production)
        optimizers_config=OptimizersConfigDiff(
            indexing_threshold=0,
        ),
    )

    # Payload indexes — lets us filter by these fields without a full scan
    # Always filter by doc_type and effective_date at retrieval time
    client.create_payload_index(
        collection_name=name,
        field_name="doc_type",
        field_schema="keyword",
    )
    client.create_payload_index(
        collection_name=name,
        field_name="effective_date",
        field_schema="datetime",
    )
    client.create_payload_index(
        collection_name=name,
        field_name="source_doc_id",
        field_schema="keyword",
    )

    print(f"  ✓ Created collection: {name}")


def setup_all_collections() -> None:
    print("\nConnecting to Qdrant...")
    client = get_client()

    # Verify connection
    info = client.get_collections()
    print(f"Connected. Existing collections: {[c.name for c in info.collections]}\n")

    print("Setting up tenant collections...")
    for tenant_id, config in TENANT_REGISTRY.items():
        name = config.rag_namespace

        if collection_exists(client, name):
            print(f"  – Skipping {name} (already exists)")
            continue

        create_collection(client, name)

    print("\nAll collections ready.")
    print("\nPayload schema per chunk (what you'll ingest):")
    print("""
    {
        "text":           str,   # the chunk text
        "source_doc_id":  str,   # e.g. "2026_benefits_summary.pdf"
        "doc_type":       str,   # "benefits" | "formulary" | "policy"
        "chunk_index":    int,   # position within the source doc
        "section":        str,   # e.g. "Section 4.2 - Outpatient Services"
        "effective_date": str,   # ISO 8601, e.g. "2026-01-01T00:00:00Z"
        "page_number":    int,   # source PDF page
        "tenant_id":      str,   # redundant safety filter
    }
    """)


if __name__ == "__main__":
    setup_all_collections()