-- Grants so PostgREST (service_role / authenticated) can use CareNav tables

GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.sessions TO authenticated, service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.turns TO authenticated, service_role;
GRANT SELECT ON public.tenant_domain_map TO service_role;

ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_domain_map ENABLE ROW LEVEL SECURITY;
