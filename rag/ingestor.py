"""
rag/ingestor.py
───────────────
Ingests benefits PDFs, formulary CSVs, and policy documents into Qdrant.

Chunking strategy:
  - PDF prose (benefits summaries, policy docs):
      Semantic chunking — split on section headers, target 512 tokens,
      overlap 64 tokens. Keeps section context with each chunk.

  - Formulary CSVs (drug tier tables):
      Table-aware chunking — one chunk per drug row, always includes
      the column headers so the chunk is self-contained.
      (Splitting mid-table was the regression the eval harness caught.)

Usage:
    python rag/ingestor.py --tenant tenant_bcbs --file path/to/doc.pdf --type benefits
    python rag/ingestor.py --tenant tenant_bcbs --file path/to/formulary.csv --type formulary
"""

import argparse
import csv
import hashlib
import io
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from openai import OpenAI

from core.settings import settings
from core.tenant import get_tenant

# ── Clients ───────────────────────────────────────────────────────────────────

def get_qdrant() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
    )


def get_openai() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_prose(text: str, max_tokens: int = 512, overlap: int = 64) -> list[dict]:
    """
    Semantic chunking for policy/benefits prose.
    Splits on section headers first, then by token estimate if still too long.
    Includes the section header in every chunk so it's self-contained.
    """
    # Split on numbered sections, lettered sections, or ALL CAPS headers
    section_pattern = re.compile(
        r"(?=\n(?:Section\s+\d+|SECTION\s+\d+|[A-Z][A-Z\s]{4,}:|\d+\.\d*\s+[A-Z]))",
        re.MULTILINE,
    )
    raw_sections = section_pattern.split(text)
    sections = [s.strip() for s in raw_sections if s.strip()]

    chunks = []
    for section in sections:
        words = section.split()
        # Rough token estimate: 1 token ≈ 0.75 words
        token_estimate = len(words) / 0.75

        if token_estimate <= max_tokens:
            chunks.append({"text": section, "section": _extract_header(section)})
        else:
            # Sliding window within an oversized section
            step = int(max_tokens * 0.75)       # words per chunk
            overlap_words = int(overlap * 0.75) # words to overlap
            header = _extract_header(section)

            for i in range(0, len(words), step - overlap_words):
                window = words[i: i + step]
                chunk_text = " ".join(window)
                chunks.append({"text": chunk_text, "section": header})

    return chunks


def chunk_formulary_csv(csv_text: str) -> list[dict]:
    """
    Table-aware chunking for formulary CSVs.
    One chunk per drug row. Header row is prepended to every chunk
    so each chunk is fully self-contained — no cross-chunk lookups needed.

    This is the fix for the regression caught by the eval harness:
    naively splitting a CSV by character count breaks rows across chunks,
    destroying the tier/PA-requirement association.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    if not rows:
        return []

    headers = list(rows[0].keys())
    header_line = ", ".join(headers)

    chunks = []
    for row in rows:
        row_line = ", ".join(f"{k}: {v}" for k, v in row.items())
        chunk_text = f"Formulary entry — {header_line}\n{row_line}"
        chunks.append({
            "text": chunk_text,
            "section": f"Formulary: {row.get('Drug Name', row.get('drug_name', 'Unknown'))}",
        })

    return chunks


def _extract_header(text: str) -> str:
    first_line = text.split("\n")[0].strip()
    return first_line[:120] if first_line else "Unknown section"


# ── Embedding ─────────────────────────────────────────────────────────────────

def embed_chunks(texts: list[str], openai_client: OpenAI) -> list[list[float]]:
    """Batch embed with text-embedding-3-small. Max 2048 inputs per call."""
    response = openai_client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )
    return [item.embedding for item in response.data]


# ── Ingest ────────────────────────────────────────────────────────────────────

def ingest_file(
    tenant_id: str,
    file_path: str,
    doc_type: str,          # "benefits" | "formulary" | "policy"
    effective_date: str = "",
) -> None:
    tenant = get_tenant(tenant_id)
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    print(f"\nIngesting: {path.name}")
    print(f"  Tenant:     {tenant_id}")
    print(f"  Collection: {tenant.rag_namespace}")
    print(f"  Doc type:   {doc_type}")

    raw_text = path.read_text(encoding="utf-8", errors="replace")

    # Choose chunking strategy by doc type
    if doc_type == "formulary" and path.suffix.lower() == ".csv":
        chunks = chunk_formulary_csv(raw_text)
        print(f"  Strategy:   table-aware (formulary CSV)")
    else:
        chunks = chunk_prose(raw_text)
        print(f"  Strategy:   semantic prose chunking")

    print(f"  Chunks:     {len(chunks)}")

    if not chunks:
        print("  WARNING: No chunks produced. Check file content.")
        return

    # Embed in batches of 100
    qdrant = get_qdrant()
    openai_client = get_openai()
    source_doc_id = path.name
    effective = effective_date or datetime.now(timezone.utc).isoformat()

    batch_size = 100
    total_inserted = 0

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i: i + batch_size]
        texts = [c["text"] for c in batch]

        print(f"  Embedding batch {i // batch_size + 1}/{-(-len(chunks) // batch_size)}...", end=" ")
        vectors = embed_chunks(texts, openai_client)
        print("done")

        points = []
        for j, (chunk, vector) in enumerate(zip(batch, vectors)):
            chunk_id = str(uuid.uuid4())
            points.append(
                PointStruct(
                    id=chunk_id,
                    vector={"dense": vector},
                    payload={
                        "text": chunk["text"],
                        "source_doc_id": source_doc_id,
                        "doc_type": doc_type,
                        "chunk_index": i + j,
                        "section": chunk.get("section", ""),
                        "effective_date": effective,
                        "page_number": 0,       # set if parsing PDFs with page info
                        "tenant_id": tenant_id, # redundant safety filter
                    },
                )
            )

        qdrant.upsert(
            collection_name=tenant.rag_namespace,
            points=points,
        )
        total_inserted += len(points)

    print(f"\n  ✓ Inserted {total_inserted} chunks into {tenant.rag_namespace}")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest documents into CareNav RAG")
    parser.add_argument("--tenant", required=True, help="Tenant ID (e.g. tenant_bcbs)")
    parser.add_argument("--file", required=True, help="Path to document file")
    parser.add_argument(
        "--type",
        required=True,
        choices=["benefits", "formulary", "policy"],
        help="Document type — controls chunking strategy",
    )
    parser.add_argument(
        "--effective-date",
        default="",
        help="ISO 8601 effective date, e.g. 2026-01-01T00:00:00Z",
    )
    args = parser.parse_args()

    ingest_file(
        tenant_id=args.tenant,
        file_path=args.file,
        doc_type=args.type,
        effective_date=args.effective_date,
    )