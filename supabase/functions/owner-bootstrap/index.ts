import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});

Deno.serve(async (request) => {
  if (request.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const suppliedToken = request.headers.get("x-hiop-bootstrap-token");
  if (!suppliedToken || suppliedToken !== Deno.env.get("HIOP_OWNER_BOOTSTRAP_TOKEN")) return json({ error: "Not authorized" }, 401);
  const { email, password, display_name } = await request.json();
  if (!email || !password || password.length < 12 || !display_name) return json({ error: "Name, email, and a 12-character password are required" }, 422);
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { count, error: countError } = await admin.from("owner_profiles").select("id", { count: "exact", head: true });
  if (countError) return json({ error: "Owner setup is unavailable" }, 500);
  if (count && count > 0) return json({ error: "The first owner has already been created" }, 409);
  const { data, error } = await admin.auth.admin.createUser({ email, password, email_confirm: true });
  if (error || !data.user) return json({ error: error?.message ?? "Unable to create owner" }, 422);
  const { error: profileError } = await admin.from("owner_profiles").insert({ id: data.user.id, email: email.toLowerCase(), display_name, role: "owner" });
  if (profileError) { await admin.auth.admin.deleteUser(data.user.id); return json({ error: "Unable to finish owner setup" }, 500); }
  await admin.from("owner_audit_events").insert({ actor_id: data.user.id, action: "OWNER_BOOTSTRAPPED", entity_type: "owner_profile", entity_id: data.user.id, description: "Created the first HIOP Owner account" });
  return json({ id: data.user.id, email: data.user.email, role: "owner" }, 201);
});
