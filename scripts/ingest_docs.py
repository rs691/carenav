"""
scripts/ingest_docs.py
──────────────────────
Create Qdrant collections (if needed) and ingest all sample plan docs under docs/.

Usage (from repo root, venv active):
    python scripts/ingest_docs.py
    python scripts/ingest_docs.py --tenant tenant_bcbs
    python scripts/ingest_docs.py --skip-setup
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.ingestor import ingest_file
from rag.setup_collections import setup_all_collections

# (relative path under docs/, tenant_id, doc_type)
DOC_MANIFEST: list[tuple[str, str, str]] = [
    ("tenant_bcbs/benefits_summary.txt", "tenant_bcbs", "benefits"),
    ("tenant_bcbs/formulary.csv", "tenant_bcbs", "formulary"),
    ("tenant_bcbs/claims_and_pa_policy.txt", "tenant_bcbs", "policy"),
    ("tenant_medicaid/benefits_summary.txt", "tenant_medicaid", "benefits"),
    ("tenant_medicaid/formulary.csv", "tenant_medicaid", "formulary"),
    ("tenant_medicaid/claims_and_pa_policy.txt", "tenant_medicaid", "policy"),
    ("tenant_employer/benefits_summary.txt", "tenant_employer", "benefits"),
    ("tenant_employer/formulary.csv", "tenant_employer", "formulary"),
    ("tenant_employer/claims_and_pa_policy.txt", "tenant_employer", "policy"),
]

DEFAULT_EFFECTIVE = "2026-09-01T00:00:00Z"


def main() -> None:
    parser = argparse.ArgumentParser(description="Setup Qdrant + ingest CareNav sample docs")
    parser.add_argument(
        "--tenant",
        default="",
        help="Only ingest for this tenant (default: all)",
    )
    parser.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip collection creation",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate collections (use when switching OpenAI <-> Ollama embeds)",
    )
    parser.add_argument(
        "--effective-date",
        default=DEFAULT_EFFECTIVE,
        help=f"ISO effective date (default {DEFAULT_EFFECTIVE})",
    )
    args = parser.parse_args()

    if not args.skip_setup:
        setup_all_collections(recreate=args.recreate)
    elif args.recreate:
        setup_all_collections(recreate=True)

    docs_root = ROOT / "docs"
    selected = [
        item
        for item in DOC_MANIFEST
        if not args.tenant or item[1] == args.tenant
    ]
    if not selected:
        raise SystemExit(f"No docs matched tenant={args.tenant!r}")

    print(f"\nIngesting {len(selected)} document(s) from {docs_root} ...")
    for rel, tenant_id, doc_type in selected:
        path = docs_root / rel
        if not path.exists():
            print(f"  [missing] {path}")
            continue
        ingest_file(
            tenant_id=tenant_id,
            file_path=str(path),
            doc_type=doc_type,
            effective_date=args.effective_date,
        )

    print("\nDone. Agents can retrieve benefits / formulary / policy chunks.")


if __name__ == "__main__":
    main()
