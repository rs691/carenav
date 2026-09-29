-- Member identity: after sign-up, each user identifies themselves as a plan
-- member (member ID + group number) or skips and stays unlinked.
--
--   plan_groups   group / plan number -> tenant (plan-level link)
--   members       roster loaded by the plan; a user claims one row (member link)
--
-- The API (service role) performs the match and writes the result into
-- auth.users.raw_app_meta_data: tenant_id, member_record_id, onboarded.

-- ── Plan groups ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.plan_groups (
    group_number  TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL,
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.plan_groups ENABLE ROW LEVEL SECURITY;
-- No policies: service_role / postgres only.

INSERT INTO public.plan_groups (group_number, tenant_id) VALUES
    ('BCBS-2026', 'tenant_bcbs'),
    ('ILMEDICAID-2026', 'tenant_medicaid'),
    ('ACME-2026', 'tenant_employer')
ON CONFLICT (group_number) DO NOTHING;

-- ── Member roster ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       TEXT NOT NULL,
    member_number   TEXT NOT NULL UNIQUE,
    group_number    TEXT NOT NULL REFERENCES public.plan_groups (group_number),
    first_name      TEXT NOT NULL,
    last_name       TEXT NOT NULL,
    coverage_tier   TEXT NOT NULL DEFAULT 'Individual',
    effective_date  DATE,
    user_id         UUID UNIQUE REFERENCES auth.users (id) ON DELETE SET NULL,
    claimed_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_members_tenant ON public.members (tenant_id);

ALTER TABLE public.members ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS members_select_own ON public.members;
CREATE POLICY members_select_own ON public.members
  FOR SELECT
  TO authenticated
  USING (user_id = (SELECT auth.uid()));

GRANT SELECT ON public.members TO authenticated;

-- Demo roster (one per plan) for local testing
INSERT INTO public.members
    (tenant_id, member_number, group_number, first_name, last_name, coverage_tier, effective_date)
VALUES
    ('tenant_bcbs', 'BCB100001', 'BCBS-2026', 'Jordan', 'Rivera', 'Family', '2026-01-01'),
    ('tenant_medicaid', 'ILM200001', 'ILMEDICAID-2026', 'Casey', 'Nguyen', 'Individual', '2026-01-01'),
    ('tenant_employer', 'ACM300001', 'ACME-2026', 'Taylor', 'Brooks', 'Employee + Spouse', '2026-01-01')
ON CONFLICT (member_number) DO NOTHING;

-- ── Tenant claim: app_metadata only ─────────────────────────────────────────
-- user_metadata is writable by the user, so it must never grant tenant access.

CREATE OR REPLACE FUNCTION public.jwt_tenant_id()
RETURNS text
LANGUAGE sql
STABLE
SET search_path = ''
AS $$
  SELECT (SELECT auth.jwt() -> 'app_metadata' ->> 'tenant_id');
$$;

-- Trigger-only function; keep it off the public RPC surface.
REVOKE ALL ON FUNCTION public.handle_new_user_tenant() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.handle_new_user_tenant() TO supabase_auth_admin;

-- ── Admin helper: link / unlink a user by email ─────────────────────────────
-- SELECT public.admin_link_member('a@b.com', 'BCB100001');   -- link to roster row
-- SELECT public.admin_link_member('a@b.com', NULL);          -- unlink

CREATE OR REPLACE FUNCTION public.admin_link_member(p_email text, p_member_number text)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_user_id uuid;
  v_member public.members%ROWTYPE;
BEGIN
  SELECT id INTO v_user_id FROM auth.users WHERE lower(email) = lower(p_email);
  IF v_user_id IS NULL THEN
    RAISE EXCEPTION 'No user with email %', p_email;
  END IF;

  UPDATE public.members SET user_id = NULL, claimed_at = NULL WHERE user_id = v_user_id;

  IF p_member_number IS NULL THEN
    UPDATE auth.users
    SET raw_app_meta_data = COALESCE(raw_app_meta_data, '{}'::jsonb)
          - 'tenant_id' - 'member_record_id'
          || jsonb_build_object('onboarded', true)
    WHERE id = v_user_id;
    RETURN;
  END IF;

  SELECT * INTO v_member FROM public.members WHERE member_number = upper(p_member_number);
  IF NOT FOUND THEN
    RAISE EXCEPTION 'No member %', p_member_number;
  END IF;

  UPDATE public.members SET user_id = v_user_id, claimed_at = NOW() WHERE id = v_member.id;
  UPDATE auth.users
  SET raw_app_meta_data = COALESCE(raw_app_meta_data, '{}'::jsonb)
        || jsonb_build_object(
             'tenant_id', v_member.tenant_id,
             'member_record_id', v_member.id,
             'onboarded', true)
  WHERE id = v_user_id;
END;
$$;

REVOKE ALL ON FUNCTION public.admin_link_member(text, text) FROM PUBLIC, anon, authenticated;
