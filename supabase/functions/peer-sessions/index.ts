/**
 * Supabase Edge Function — list non-revoked crypto session public keys for a tenant.
 *
 * JWT-gated peer discovery at the edge (complements FastAPI GET /api/v1/sessions).
 * Never returns private keys. Deploy with: supabase functions deploy peer-sessions
 *
 * Query: ?tenant_id=<uuid>
 */

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

// --- Explicit CORS allow-list (no wildcard in production) ---
const ALLOWED_ORIGINS = new Set([
  "https://forjd.co",
  "https://www.forjd.co",
  "https://backend.forjd.co",
  "https://deml.app",
  "https://backend.deml.app",
  "http://localhost:4200",
  "http://127.0.0.1:4200",
]);

// --- Browser hardening (merged with CORS; never overrides Allow-Origin) ---
const SECURITY_HEADERS: Record<string, string> = {
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "Referrer-Policy": "no-referrer",
  "Permissions-Policy":
    "geolocation=(), microphone=(), camera=(), payment=(), usb=(), bluetooth=(), interest-cohort=(), browsing-topics=()",
  // Edge is HTTPS-only in production; HSTS is safe for forjd.co / deml.app callers.
  "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
  "Cache-Control": "no-store",
};

function corsHeaders(req: Request): Record<string, string> {
  const origin = (req.headers.get("Origin") || "").trim();
  const allowOrigin = ALLOWED_ORIGINS.has(origin) ? origin : "https://forjd.co";
  return {
    "Access-Control-Allow-Origin": allowOrigin,
    "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
    "Vary": "Origin",
  };
}

function responseHeaders(req: Request, extra: Record<string, string> = {}): Record<string, string> {
  return { ...SECURITY_HEADERS, ...corsHeaders(req), ...extra };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: responseHeaders(req) });
  }

  try {
    const authHeader = req.headers.get("Authorization");
    if (!authHeader) {
      return new Response(JSON.stringify({ error: "missing Authorization" }), {
        status: 401,
        headers: responseHeaders(req, { "Content-Type": "application/json" }),
      });
    }

    const url = new URL(req.url);
    const tenantId = url.searchParams.get("tenant_id");
    if (!tenantId) {
      return new Response(JSON.stringify({ error: "tenant_id required" }), {
        status: 400,
        headers: responseHeaders(req, { "Content-Type": "application/json" }),
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
        headers: responseHeaders(req, { "Content-Type": "application/json" }),
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
      return new Response(JSON.stringify({ error: "query failed" }), {
        status: 500,
        headers: responseHeaders(req, { "Content-Type": "application/json" }),
      });
    }

    return new Response(JSON.stringify({ ok: true, tenant_id: tenantId, sessions: data ?? [] }), {
      headers: responseHeaders(req, { "Content-Type": "application/json" }),
    });
  } catch {
    return new Response(JSON.stringify({ error: "internal error" }), {
      status: 500,
      headers: responseHeaders(req, { "Content-Type": "application/json" }),
    });
  }
});
