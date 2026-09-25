-- Auto-set app_metadata.tenant_id from email domain on signup

CREATE OR REPLACE FUNCTION public.handle_new_user_tenant()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  email_domain text;
  mapped_tenant text;
BEGIN
  IF NEW.email IS NULL OR position('@' in NEW.email) = 0 THEN
    RETURN NEW;
  END IF;

  email_domain := lower(split_part(NEW.email, '@', 2));

  SELECT t.tenant_id INTO mapped_tenant
  FROM public.tenant_domain_map t
  WHERE t.domain = email_domain;

  IF mapped_tenant IS NOT NULL THEN
    NEW.raw_app_meta_data :=
      COALESCE(NEW.raw_app_meta_data, '{}'::jsonb)
      || jsonb_build_object('tenant_id', mapped_tenant);
  END IF;

  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS on_auth_user_created_set_tenant ON auth.users;
CREATE TRIGGER on_auth_user_created_set_tenant
  BEFORE INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user_tenant();

GRANT EXECUTE ON FUNCTION public.jwt_tenant_id() TO authenticated;
