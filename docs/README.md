# Sample plan documents for CareNav RAG

These files are ingested into per-tenant Qdrant collections so benefits,
formulary, claims, and prior-auth agents have real grounding text.

| Tenant | Files | Doc types |
|---|---|---|
| `tenant_bcbs` | `benefits_summary.txt`, `formulary.csv`, `claims_and_pa_policy.txt` | benefits, formulary, policy |
| `tenant_medicaid` | same pattern | benefits, formulary, policy |
| `tenant_employer` | same pattern | benefits, formulary, policy |

## Ingest

From the repo root (venv active, `.env` with OpenAI + Qdrant keys):

```powershell
python scripts/ingest_docs.py
```

Or step by step:

```powershell
python rag/setup_collections.py
python rag/ingestor.py --tenant tenant_bcbs --file docs/tenant_bcbs/benefits_summary.txt --type benefits --effective-date 2026-09-01T00:00:00Z
python rag/ingestor.py --tenant tenant_bcbs --file docs/tenant_bcbs/formulary.csv --type formulary --effective-date 2026-09-01T00:00:00Z
python rag/ingestor.py --tenant tenant_bcbs --file docs/tenant_bcbs/claims_and_pa_policy.txt --type policy --effective-date 2026-09-01T00:00:00Z
```

Replace sample text with real SPDs/PDFs as needed (`ingestor.py` supports `.pdf` via pdfplumber).
