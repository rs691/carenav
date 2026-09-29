# CareNav — Multi-Tenant Healthcare Benefits Assistant

CareNav is a multi-agent AI platform that helps health-plan members get clear answers about **coverage, formulary drugs, claims, and prior authorizations**.

A member asks a question in the chat UI. The FastAPI backend authenticates the request, loads conversation history, runs a **LangGraph** orchestrator that classifies intent and routes to a specialist agent, retrieves **tenant-scoped** plan documents from **Qdrant**, applies **PHI and tone guardrails**, and returns a compliant reply. Turns are persisted in **Supabase**; the **Next.js** frontend handles login/signup and the chat experience.

---

## What the product does

| Member need | What CareNav does |
|---|---|
| “Is an MRI covered?” | Benefits agent looks up plan coverage language via RAG |
| “Is Ozempic on formulary?” | Formulary agent searches the tenant drug list |
| “Where is my claim?” | Claims agent answers status-style questions from policy context |
| “Do I need prior auth?” | Prior-auth agent explains requirements from policy docs |
| Frustrated / complex cases | Escalation agent routes to human-friendly handoff language |

Each tenant (health plan / employer group) has its own:

- Plan name and tone profile (e.g. empathetic plain language vs clinical formal)
- Enabled agent set (Medicaid may not expose claims, for example)
- Isolated RAG namespace in Qdrant
- Optional SSO / email-domain → tenant mapping in Supabase

---

## High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js frontend (frontend/)                               │
│  Login / Signup (shadcn) · Sidebar · Chat · Theme (dark/light)│
│  Supabase Auth (browser) → access_token → API               │
└────────────────────────────┬────────────────────────────────┘
                             │ POST /chat
                             │ Authorization: Bearer <jwt>
                             │ x-tenant-id (dev fallback)
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI (api/main.py)                                      │
│  CORS · JWT (JWKS ES256) or x-tenant-id header              │
│  Load session → invoke graph → save turn                    │
└────────────────────────────┬────────────────────────────────┘
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  LangGraph orchestrator (orchestrator/graph.py)             │
│                                                             │
│  PHI scrub → classify intent → retrieve RAG chunks          │
│       → route agent → guardrails (PHI / tone) → respond     │
│                                                             │
│  Agents: benefits · formulary · claims · prior_auth ·       │
│          escalation                                         │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
        Qdrant (rag/)                  Supabase (core/session.py)
        Per-tenant collections         sessions + turns (REST or
        Hybrid retrieval               in-memory fallback)
```

### Request lifecycle (chat)

1. Frontend sends `{ member_id, session_id, message }` with optional Bearer token.
2. Auth resolves tenant from JWT `app_metadata.tenant_id` / `user_metadata.tenant_id`, or from `x-tenant-id` in development.
3. Prior turns load from Supabase (or memory).
4. Graph scrubbs PHI from the query, classifies intent (LLM when `OPENAI_API_KEY` is set; keyword fallback otherwise).
5. Retriever pulls tenant-scoped chunks from Qdrant for the intent’s document type.
6. The matching agent runs under an SLA timeout (`AgentContract`).
7. Guardrails scrub PHI and normalize tone to the tenant profile.
8. Assistant turn is saved; API returns `reply`, `agent_used`, `intent`, `confidence`, `phi_scrubbed`, `turn_count`.

---

## Stack

| Layer | Local / free | Notes |
|---|---|---|
| Orchestration | LangGraph | State carried in `MemberSession` |
| LLM | Ollama `llama3.2:3b` (free local) or OpenAI `gpt-4o-mini` | Azure OpenAI |
| Embeddings | Ollama `nomic-embed-text` or OpenAI `text-embedding-3-small` | Azure OpenAI |
| Vector DB | Qdrant Cloud or Docker | One collection namespace per tenant |
| Database / Auth | Supabase | Postgres + Auth + optional Edge Function |
| API | FastAPI + Uvicorn | Binds `0.0.0.0` in Docker / Render |
| Frontend | Next.js 16 + React 19 | shadcn/ui (login-03, signup-03, sidebar-01) |
| Theme | Custom `ThemeProvider` | Light / dark / system (`dark-mode.md`) |
| Eval | Golden set + CI workflow | Offline unit tests; optional live eval |

---

## Repository layout

```
carenav/
├── agents/                 # Specialist agents (AgentContract)
│   ├── base.py             # AgentResult, MemberContext, protocol
│   ├── benefits.py
│   ├── formulary.py
│   ├── claims.py
│   ├── prior_auth.py
│   ├── escalation.py
│   └── rag_lookup.py       # Shared RAG call helpers
├── api/
│   └── main.py             # /health, /chat
├── core/
│   ├── settings.py         # pydantic-settings (.env first)
│   ├── tenant.py           # Dev tenant registry
│   └── session.py          # Supabase REST → asyncpg → memory
├── middleware/
│   ├── auth.py             # JWKS ES256 / HS256 + x-tenant-id
│   └── guardrails.py       # PHI scrub + tone
├── orchestrator/
│   ├── graph.py            # LangGraph wiring + AGENT_REGISTRY
│   └── classifier.py       # Intent enum + LLM/keyword classify
├── prompts/                # Versioned YAML prompts + registry
├── rag/
│   ├── setup_collections.py
│   ├── ingestor.py         # PDF / CSV → embeddings → Qdrant
│   └── retriever.py
├── supabase/
│   ├── migrations/         # sessions, turns, RLS, tenant map
│   └── functions/set-tenant/
├── frontend/               # Next.js app
│   ├── app/login, signup, settings, [...]/chat/[chatid]
│   ├── components/         # chat UI, sidebar, theme, shadcn
│   └── lib/supabase/       # browser + server + middleware clients
├── evals/                  # golden_set.csv + runner.py
├── tests/                  # Offline pytest suite
├── scripts/                # Smoke helpers for DB/REST
├── docker-compose.yml      # API + local Qdrant
├── Dockerfile
├── pyproject.toml
├── requirements.txt
├── .env.example            # Backend secrets template
└── env.example             # Same template (legacy name)
```

---

## Prerequisites

- **Python 3.12+** (venv recommended)
- **Node.js 20+** (for `frontend/`)
- **Ollama** (recommended free path) with `llama3.2:3b` + `nomic-embed-text`, **or** an OpenAI API key with credits
- **Qdrant** (Cloud free tier or `docker compose` service)
- **Supabase project** (Auth + DB; optional locally — sessions fall back to memory)

---

## Quick start — backend

```powershell
# From repo root
python -m venv .venv
.venv\Scripts\Activate.ps1

# Install (either works)
pip install -r requirements.txt
# or: pip install -e ".[dev]"

copy .env.example .env
# Edit .env — at minimum OPENAI_API_KEY, QDRANT_*, CORS_ORIGINS
# Add SUPABASE_URL + SUPABASE_SERVICE_KEY for durable sessions

# Local Qdrant via Docker (optional if using Qdrant Cloud)
docker compose up qdrant -d

# Point QDRANT_URL at http://localhost:6333 when using compose Qdrant
python rag/setup_collections.py

# API (default http://127.0.0.1:8000)
# If port 8000 is busy on Windows, use --port 8001 and set NEXT_PUBLIC_API_URL
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Health check:

```powershell
curl http://127.0.0.1:8000/health
```

### Backend environment (`.env`)

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `ollama` (free local) or `openai` |
| `OPENAI_API_KEY` | Required only when `LLM_PROVIDER=openai` |
| `OPENAI_MODEL` | Default `gpt-4o-mini` |
| `OPENAI_EMBEDDING_MODEL` | Default `text-embedding-3-small` (dim 1536) |
| `OLLAMA_BASE_URL` | Default `http://127.0.0.1:11434` (avoids `localhost` resolving to IPv6 `::1`, where a WSL/Docker Ollama may answer instead) |
| `OLLAMA_MODEL` | Default `llama3.2:3b` |
| `OLLAMA_EMBEDDING_MODEL` | Default `nomic-embed-text` (dim 768) |
| `QDRANT_URL` / `QDRANT_API_KEY` | Vector store |
| `SUPABASE_URL` | Project URL (also drives JWKS URL) |
| `SUPABASE_SERVICE_KEY` | Service role for session REST writes |
| `SUPABASE_JWKS_URL` | Optional override; else `{SUPABASE_URL}/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_SECRET` | Only for legacy HS256 projects |
| `DATABASE_URL` | Optional direct Postgres; REST path is preferred on Windows |
| `CORS_ORIGINS` | e.g. `http://localhost:3000` |
| `APP_ENV` | `development` enables private-LAN CORS regex |
| `LOG_LEVEL` | `INFO` / `DEBUG` |

Settings load **dotenv / `.env` before machine environment variables**, so a wrong global `SUPABASE_URL` will not silently override the project file.

---

## Quick start — frontend

```powershell
cd frontend
copy ..\.env.local.example .env.local
# Set at least:
#   NEXT_PUBLIC_SUPABASE_URL=
#   NEXT_PUBLIC_SUPABASE_ANON_KEY=
#   NEXT_PUBLIC_API_URL=http://localhost:8000

npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Home redirects into a new chat session under `/en/default/chat/<id>`.

### Frontend routes

| Route | Description |
|---|---|
| `/` | Starts a new chat |
| `/en/default/chat/[chatid]` | Chat UI for a session |
| `/login` | shadcn login-03 — password + magic link |
| `/signup` | shadcn signup-03 — email/password signup |
| `/settings` | Dev tenant picker + appearance toggle |
| `/auth/callback` | Supabase OAuth / magic-link callback |

### UI notes

- **Auth pages** use full-bleed muted backgrounds (login-03 / signup-03); sidebar is hidden.
- **App shell** uses sidebar-01: CareNav brand, new chat, settings, sign in/out, theme toggle.
- **Dark / light / system** via `components/theme-provider.tsx` and `components/mode-toggle.tsx` (see `dark-mode.md`).

### Frontend environment (`frontend/.env.local`)

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Same Supabase project as the API |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public anon key |
| `NEXT_PUBLIC_API_URL` | FastAPI base URL (default `http://localhost:8000`) |
| `NEXT_PUBLIC_AUTH_REQUIRED` | Set `true` to force login in middleware |

---

## Docker (API + Qdrant)

```bash
cp .env.example .env   # fill keys
docker compose up
```

- API: `http://localhost:8000` (hot-reload via volume mount)
- Qdrant: `http://localhost:6333`
- Supabase stays cloud-hosted; set `SUPABASE_*` in `.env`
- Frontend is not in compose — run it with `npm run dev` separately

The Dockerfile installs Python deps with `uv` and starts Uvicorn on `0.0.0.0:8000`. On platforms like **Render**, bind to `0.0.0.0` and use `$PORT` if the host injects it.

---

## Ingest plan documents

Sample SPDs and formularies live under `docs/<tenant_id>/`. With Ollama running:

```powershell
# First time / after switching OpenAI <-> Ollama embeds:
python scripts/ingest_docs.py --recreate

# Later re-ingests (collections already sized correctly):
python scripts/ingest_docs.py
```

Or step by step:

```powershell
python rag/setup_collections.py

# Benefits (txt or PDF)
python rag/ingestor.py --tenant tenant_bcbs --file docs/tenant_bcbs/benefits_summary.txt --type benefits --effective-date 2026-09-01T00:00:00Z

# Formulary CSV
python rag/ingestor.py --tenant tenant_bcbs --file docs/tenant_bcbs/formulary.csv --type formulary --effective-date 2026-09-01T00:00:00Z

# Claims / prior-auth policy
python rag/ingestor.py --tenant tenant_bcbs --file docs/tenant_bcbs/claims_and_pa_policy.txt --type policy --effective-date 2026-09-01T00:00:00Z
```

Chunks are embedded and stored under the tenant’s RAG namespace from `core/tenant.py` (e.g. `tenant_bcbs_2026`). Without ingested docs, agents fall back to “couldn’t find that in your plan documents.”

---

## API reference

### `GET /health`

```json
{ "status": "ok", "service": "carenav" }
```

### `POST /chat`

**Headers**

| Header | When |
|---|---|
| `Authorization: Bearer <supabase_access_token>` | Production / signed-in users |
| `x-tenant-id: tenant_bcbs` | Dev without JWT, or fallback when JWT has no tenant claim |
| `Content-Type: application/json` | Always |

**Body**

```json
{
  "member_id": "uuid-or-local-id",
  "session_id": "uuid",
  "message": "Is my MRI covered under this plan?"
}
```

When a JWT is present, `member_id` is taken from the token subject (`sub`).

**Response**

```json
{
  "reply": "...",
  "agent_used": "benefits",
  "intent": "benefits_lookup",
  "confidence": 0.91,
  "phi_scrubbed": false,
  "turn_count": 3
}
```

Interactive docs: `http://127.0.0.1:8000/docs`

---

## Multi-tenancy

Dev seed configs live in `core/tenant.py`:

| Tenant ID | Plan | Enabled agents (typical) |
|---|---|---|
| `tenant_bcbs` | BlueCross Premier PPO | benefits, formulary, claims, prior_auth, escalation |
| `tenant_medicaid` | Illinois Medicaid | benefits, formulary, escalation |
| `tenant_employer` | Acme Corp Benefits | benefits, claims, escalation |

Each tenant also sets `rag_namespace`, `formulary_version`, `tone_profile`, and `sso_provider`.

In production, tenant identity should come from the JWT. Supabase migrations include:

- `sessions` / `turns` — conversation persistence  
- `tenant_domain_map` — email domain → tenant  
- RLS + grants for the Data API  
- Auth trigger / Edge Function hooks for attaching `tenant_id` at signup/login  

The `set-tenant` Edge Function (`supabase/functions/set-tenant/`) maps domains into JWT metadata.

---

## Agents and intents

| Intent | Agent | Typical docs |
|---|---|---|
| `benefits_lookup` | `benefits` | benefits PDFs |
| `formulary_lookup` | `formulary` | formulary CSV / drug lists |
| `claim_status` | `claims` | policy / claims guidance |
| `prior_auth_status` | `prior_auth` | prior-auth policy |
| `escalation` | `escalation` | (handoff copy; no RAG required) |

All agents implement `AgentContract` in `agents/base.py`:

- `agent_id`, `latency_sla_ms`
- `async def run(ctx: MemberContext) -> AgentResult`

### Adding a new agent

1. Create `agents/your_agent.py` implementing `AgentContract`.
2. Register it in `AGENT_REGISTRY` in `orchestrator/graph.py`.
3. Add a graph node + edge in `build_graph()`.
4. Map an intent in `INTENT_TO_AGENT` / classifier enums.
5. Add a versioned prompt under `prompts/` and register it.
6. Add rows to `evals/golden_set.csv`.
7. Run `pytest` and `python evals/runner.py`.

---

## Auth model

**Frontend**

- Supabase Auth email/password and magic link
- Session access token stored for API calls (`sessionStorage` + middleware refresh)
- Signup stores `full_name` in user metadata

**Backend**

- Prefers verifying Supabase JWTs via **JWKS (ES256)** from  
  `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
- Falls back to **HS256** with `SUPABASE_JWT_SECRET` for older projects
- Without a Bearer token, accepts `x-tenant-id` for local development

---

## Tests and evals

```powershell
# Offline unit tests (no live keys required for core graph tests)
pytest tests/ -v

# Eval harness against golden_set.csv
python evals/runner.py
python evals/runner.py --save-baseline
python evals/runner.py --baseline evals/results/baseline.json
```

CI (`.github/workflows/eval.yml`) runs on push/PR to `main` and on a nightly schedule: installs deps with `uv`, runs pytest, and can compare eval results to baseline.

---

## Deployment notes

| Piece | Suggested host |
|---|---|
| FastAPI | Render / Azure Container Apps / any Docker host — bind `0.0.0.0:$PORT` |
| Next.js | Vercel or Azure Static Web Apps |
| Postgres + Auth | Supabase |
| Vectors | Qdrant Cloud |

**Render tip:** the filesystem is ephemeral; do not rely on local writes. Keep sessions in Supabase and vectors in Qdrant. Free web services spin down after idle time.

Set production `CORS_ORIGINS` to your real frontend origin(s). Set `APP_ENV=production` so the loose LAN CORS regex is not enabled.

---

## Example end-to-end flow

1. Start Qdrant (or use Cloud) and the API with a valid `.env`.
2. Ingest a benefits PDF for `tenant_bcbs`.
3. Start the frontend with Supabase URL/anon key and `NEXT_PUBLIC_API_URL`.
4. Open `/signup`, create an account (or use `/login`).
5. Ask: *“Does my plan cover outpatient MRI?”*
6. Confirm `/chat` returns a benefits agent reply and that a turn appears in Supabase `turns` (when service key is configured).

Without OpenAI or docs, the system still classifies with keywords and returns guarded fallbacks — useful for UI and auth wiring checks.

---

## License / status

Internal / prototype platform (`version 0.1.0`). Treat PHI handling as defense-in-depth (scrubbing + RLS + least-privilege keys); complete a security review before any production PHI workload.
