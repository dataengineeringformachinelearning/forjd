/**
 * Supabase Edge Function — list non-revoked crypto session public keys for a tenant.
 *
 * JWT-gated peer discovery at the edge (complements FastAPI GET /api/v1/sessions).
 * Never returns private keys. Deploy with: supabase functions deploy peer-sessions
 *
 * Query: ?tenant_id=<uuid>
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: cors });
  }

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) {
      return new Response(JSON.stringify({ error: "missing Authorization" }), {
        status: 401,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }

    const url = new URL(req.url);
    const tenantId = url.searchParams.get("tenant_id");
    if (!tenantId) {
      return new Response(JSON.stringify({ error: "tenant_id required" }), {
        status: 400,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }

    const supabase = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_ANON_KEY") ?? "",
      { global: { headers: { Authorization: authHeader } } },
    );

    const { data: membership, error: memErr } = await supabase
      .from("tenant_members")
      .select("role")
      .eq("tenant_id", tenantId)
      .maybeSingle();

    if (memErr || !membership) {
      return new Response(JSON.stringify({ error: "forbidden" }), {
        status: 403,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }

    const { data, error } = await supabase
      .from("crypto_sessions")
      .select(
        "session_id, identity_public_key, ephemeral_public_key, ratchet_state_hint, updated_at, expires_at",
      )
      .eq("tenant_id", tenantId)
      .is("revoked_at", null)
      .order("updated_at", { ascending: false })
      .limit(50);

    if (error) {
      return new Response(JSON.stringify({ error: error.message }), {
        status: 500,
        headers: { ...cors, "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify({ ok: true, tenant_id: tenantId, sessions: data ?? [] }), {
      headers: { ...cors, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...cors, "Content-Type": "application/json" },
    });
  }
});
