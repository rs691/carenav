-- CareNav conversation persistence

CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    member_id   TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_tenant ON sessions (tenant_id);

CREATE TABLE IF NOT EXISTS turns (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    TEXT NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    tenant_id     TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content       TEXT NOT NULL,
    agent_id      TEXT,
    intent        TEXT,
    confidence    DOUBLE PRECISION,
    phi_scrubbed  BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms    INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_turns_session_tenant ON turns (session_id, tenant_id);
