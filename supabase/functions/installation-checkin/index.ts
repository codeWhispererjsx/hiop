import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async (request) => {
  if (request.method !== "POST") return json({ error: "Method not allowed" }, 405);
  const authorization = request.headers.get("authorization") ?? "";
  const secret = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
  const payload = await request.json();
  if (!payload.installation_key || !secret) return json({ error: "Installation credentials are required" }, 401);
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: installation, error } = await admin.from("desktop_installations").select("id,status,activation_secret_hash").eq("installation_key", payload.installation_key).maybeSingle();
  if (error || !installation || installation.status !== "active") return json({ error: "Installation is not active" }, 401);
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(secret));
  const suppliedHash = Array.from(new Uint8Array(digest)).map((value) => value.toString(16).padStart(2, "0")).join("");
  if (suppliedHash !== installation.activation_secret_hash) return json({ error: "Installation credentials are invalid" }, 401);
  const record = {
    installation_id: installation.id,
    app_version: String(payload.app_version ?? "unknown").slice(0, 40),
    local_service_status: ["healthy", "degraded", "unavailable"].includes(payload.local_service_status) ? payload.local_service_status : "unavailable",
    monitored_devices: Math.max(0, Number(payload.monitored_devices ?? 0)),
    active_alerts: Math.max(0, Number(payload.active_alerts ?? 0)),
    last_scan_at: payload.last_scan_at ?? null,
    last_monitoring_at: payload.last_monitoring_at ?? null,
  };
  const { error: writeError } = await admin.from("installation_checkins").insert(record);
  if (writeError) return json({ error: "Unable to record check-in" }, 500);
  await admin.from("desktop_installations").update({ app_version: record.app_version, last_check_in_at: new Date().toISOString(), updated_at: new Date().toISOString() }).eq("id", installation.id);
  return json({ status: "accepted" }, 202);
});
