-- Enable RLS on CareNav tables + policies for authenticated members.
-- service_role / postgres connection used by FastAPI still bypasses RLS (Supabase default).
-- anon has no access. authenticated is scoped to JWT sub + app_metadata.tenant_id.

-- ── Indexes used by RLS predicates ───────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_sessions_member ON sessions (member_id);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_member ON sessions (tenant_id, member_id);
CREATE INDEX IF NOT EXISTS idx_turns_tenant ON turns (tenant_id);

-- ── Enable RLS ───────────────────────────────────────────────────────────────

ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_domain_map ENABLE ROW LEVEL SECURITY;

-- ── Helper: tenant claim from JWT (evaluated once per statement) ─────────────

CREATE OR REPLACE FUNCTION public.jwt_tenant_id()
RETURNS text
LANGUAGE sql
STABLE
AS $$
  SELECT COALESCE(
    (SELECT auth.jwt() -> 'app_metadata' ->> 'tenant_id'),
    (SELECT auth.jwt() -> 'user_metadata' ->> 'tenant_id')
  );
$$;

REVOKE ALL ON FUNCTION public.jwt_tenant_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.jwt_tenant_id() TO authenticated;

-- ── sessions ─────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS sessions_select_own ON sessions;
DROP POLICY IF EXISTS sessions_insert_own ON sessions;
DROP POLICY IF EXISTS sessions_update_own ON sessions;
DROP POLICY IF EXISTS sessions_delete_own ON sessions;

CREATE POLICY sessions_select_own ON sessions
  FOR SELECT
  TO authenticated
  USING (
    member_id = (SELECT auth.uid())::text
    AND tenant_id = (SELECT public.jwt_tenant_id())
  );

CREATE POLICY sessions_insert_own ON sessions
  FOR INSERT
  TO authenticated
  WITH CHECK (
    member_id = (SELECT auth.uid())::text
    AND tenant_id = (SELECT public.jwt_tenant_id())
  );

CREATE POLICY sessions_update_own ON sessions
  FOR UPDATE
  TO authenticated
  USING (
    member_id = (SELECT auth.uid())::text
    AND tenant_id = (SELECT public.jwt_tenant_id())
  )
  WITH CHECK (
    member_id = (SELECT auth.uid())::text
    AND tenant_id = (SELECT public.jwt_tenant_id())
  );

CREATE POLICY sessions_delete_own ON sessions
  FOR DELETE
  TO authenticated
  USING (
    member_id = (SELECT auth.uid())::text
    AND tenant_id = (SELECT public.jwt_tenant_id())
  );

-- ── turns ────────────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS turns_select_own ON turns;
DROP POLICY IF EXISTS turns_insert_own ON turns;
DROP POLICY IF EXISTS turns_update_own ON turns;
DROP POLICY IF EXISTS turns_delete_own ON turns;

CREATE POLICY turns_select_own ON turns
  FOR SELECT
  TO authenticated
  USING (
    tenant_id = (SELECT public.jwt_tenant_id())
    AND EXISTS (
      SELECT 1
      FROM sessions s
      WHERE s.id = turns.session_id
        AND s.tenant_id = turns.tenant_id
        AND s.member_id = (SELECT auth.uid())::text
    )
  );

CREATE POLICY turns_insert_own ON turns
  FOR INSERT
  TO authenticated
  WITH CHECK (
    tenant_id = (SELECT public.jwt_tenant_id())
    AND EXISTS (
      SELECT 1
      FROM sessions s
      WHERE s.id = turns.session_id
        AND s.tenant_id = turns.tenant_id
        AND s.member_id = (SELECT auth.uid())::text
    )
  );

CREATE POLICY turns_update_own ON turns
  FOR UPDATE
  TO authenticated
  USING (
    tenant_id = (SELECT public.jwt_tenant_id())
    AND EXISTS (
      SELECT 1
      FROM sessions s
      WHERE s.id = turns.session_id
        AND s.tenant_id = turns.tenant_id
        AND s.member_id = (SELECT auth.uid())::text
    )
  )
  WITH CHECK (
    tenant_id = (SELECT public.jwt_tenant_id())
    AND EXISTS (
      SELECT 1
      FROM sessions s
      WHERE s.id = turns.session_id
        AND s.tenant_id = turns.tenant_id
        AND s.member_id = (SELECT auth.uid())::text
    )
  );

CREATE POLICY turns_delete_own ON turns
  FOR DELETE
  TO authenticated
  USING (
    tenant_id = (SELECT public.jwt_tenant_id())
    AND EXISTS (
      SELECT 1
      FROM sessions s
      WHERE s.id = turns.session_id
        AND s.tenant_id = turns.tenant_id
        AND s.member_id = (SELECT auth.uid())::text
    )
  );

-- ── tenant_domain_map (no client access; API/service_role only) ──────────────

DROP POLICY IF EXISTS tenant_domain_map_no_client ON tenant_domain_map;

-- Explicit deny for anon/authenticated: no policies granted = no access with RLS on.
-- (Keep table readable only via service_role / postgres.)
