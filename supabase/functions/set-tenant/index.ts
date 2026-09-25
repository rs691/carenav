/**
 * Map email domain → tenant_id (for Auth hooks / admin tooling).
 */
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const supabase = createClient(
  Deno.env.get("SUPABASE_URL") ?? "",
  Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "",
);

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  const payload = await req.json();
  const email: string | undefined = payload?.user?.email ?? payload?.email;
  if (!email || !email.includes("@")) {
    return new Response(JSON.stringify({ tenant_id: null }), {
      headers: { "Content-Type": "application/json" },
    });
  }

  const domain = email.split("@")[1]!.toLowerCase();
  const { data, error } = await supabase
    .from("tenant_domain_map")
    .select("tenant_id")
    .eq("domain", domain)
    .maybeSingle();

  if (error) {
    return new Response(JSON.stringify({ error: error.message }), { status: 500 });
  }

  return new Response(
    JSON.stringify({ tenant_id: data?.tenant_id ?? null, domain }),
    { headers: { "Content-Type": "application/json" } },
  );
});
