# CareNav — Multi-Tenant Healthcare AI Benefits Platform

A production-grade multi-agent orchestration system for health insurance member support.
Members ask questions about coverage, prescriptions, claims, and prior authorizations.
LangGraph routes each question to the right agent, retrieves relevant plan documents,
and returns a compliant, PHI-safe, tone-normalized response.

## Architecture

```
Member query
    │
    ▼
LangGraph orchestrator (orchestrator/graph.py)
    │  PHI scrub → intent classify → route
    ▼
┌──────────┬────────────┬──────────┬────────────┬────────────┐
│ Benefits │ Formulary  │  Claims  │ Prior Auth │ Escalation │
└──────────┴────────────┴──────────┴────────────┴────────────┘
    │              │          │           │
    ▼              ▼          ▼           ▼
         RAG pipeline (rag/retriever.py)
         Qdrant hybrid search — per-tenant namespace
    │
    ▼
Guardrail layer (middleware/guardrails.py)
    PHI scrub · tone normalize · compliance envelope
    │
    ▼
Supabase (core/session.py)
    Save turn · load history · multi-turn context
```

## Stack

| Layer | Free / local | Production target |
|---|---|---|
| Orchestration | LangGraph | LangGraph |
| LLM | OpenAI gpt-4o-mini | Azure OpenAI |
| Embeddings | text-embedding-3-small | Azure OpenAI |
| Vector DB | Qdrant Cloud free | Azure AI Search |
| Database | Supabase free | Azure PostgreSQL |
| Auth / SSO | Supabase Auth + SAML | Azure AD B2C |
| API | FastAPI | Azure Container Apps |
| Frontend | Next.js (Vercel free) | Azure Static Web Apps |

## Quick start (Windows)

```powershell
# 1. Run setup
.\setup.ps1

# 2. Fill in your keys
copy .env.example .env
# (or copy env.example — same contents)
# Edit .env with your OpenAI, Qdrant, and Supabase keys

# 3. Activate venv
.venv\Scripts\Activate.ps1

# 4. Set up Qdrant collections
python rag/setup_collections.py

# 5. Start the API
uvicorn api.main:app --reload

# 6. (Optional) Run with Docker
docker compose up
```

## Or with Docker (one command)

```bash
cp .env.example .env   # fill in keys
docker compose up
```

## Ingest documents

```powershell
# Benefits PDF
python rag/ingestor.py --tenant tenant_bcbs --file docs/benefits.pdf --type benefits --effective-date 2026-01-01T00:00:00Z

# Formulary CSV
python rag/ingestor.py --tenant tenant_bcbs --file docs/formulary.csv --type formulary --effective-date 2026-01-01T00:00:00Z
```

## Run tests

```powershell
pytest tests/ -v
```

## Run eval harness

```powershell
# Full run
python evals/runner.py

# Save as baseline
python evals/runner.py --save-baseline

# Regression check against baseline
python evals/runner.py --baseline evals/results/baseline.json
```

## API

```
GET  /health
POST /chat

Headers:
  x-tenant-id: tenant_bcbs          # development (no JWT)
  Authorization: Bearer <jwt>        # production

Body:
  { "member_id": "uuid", "session_id": "uuid", "message": "Is my MRI covered?" }
```

## Adding a new agent

1. Create `agents/your_agent.py` implementing `AgentContract`
2. Register it in `AGENT_REGISTRY` in `orchestrator/graph.py`
3. Add a node and edge in `build_graph()`
4. Map an intent to it in `INTENT_TO_AGENT`
5. Add golden set rows in `evals/golden_set.csv`
6. Run `pytest` and `python evals/runner.py`

## Tenants

Configured in `core/tenant.py` (dev) and the `tenants` table (production).

| Tenant ID | Plan |
|---|---|
| `tenant_bcbs` | BlueCross Premier PPO |
| `tenant_medicaid` | Illinois Medicaid |
| `tenant_employer` | Acme Corp Benefits |

## SSO

Supabase Auth with SAML 2.0. Configure providers in the Supabase dashboard.
The `set-tenant` Edge Function (`supabase/functions/set-tenant/index.ts`)
maps email domains to tenant IDs in the JWT at login time.

Domain → tenant mapping lives in the `tenant_domain_map` table.

## Project structure

```
carenav/
├── agents/             # One file per agent, all implement AgentContract
├── api/                # FastAPI app + routes
├── core/               # Settings, tenant config, session persistence
├── evals/              # Golden set, runner, metrics, results/
├── middleware/         # PHI guardrails, tone normalization, JWT auth
├── orchestrator/       # LangGraph graph, LLM intent classifier
├── prompts/            # Versioned YAML prompts + registry
├── rag/                # Ingestor, retriever, PDF parser, collection setup
├── supabase/           # Edge Functions (set-tenant auth hook)
├── tests/              # 25 tests, all offline (no API keys needed)
├── .github/workflows/  # CI — eval harness + regression check
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```