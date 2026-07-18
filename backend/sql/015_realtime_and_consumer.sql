-- =============================================================================
-- FORJD Realtime + consumer feed (universal SaaS / subprocessors)
-- =============================================================================
-- Apply after 014_service_accounts.sql.
--
-- Goals:
--   • Publish stream_results (and optional sealed event metadata) to Supabase
--     Realtime so UIs / subprocessors can subscribe instead of only polling.
--   • projection_feed view — consumer-safe columns only (never ciphertext).
--   • Cursor-friendly indexes for GET /projections?since=…
--   • Default service-account scopes include sessions:* so subprocessors can
--     register X25519 public keys when REQUIRE_CRYPTO_SESSION=true.
--
-- Subprocessor note:
--   Partners keep their own end-user auth. They poll or Realtime-subscribe to
--   stream_results / projection_feed with a tenant-bound fjsvc_ token.
--   FORJD never accepts partner end-user tokens.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Cursor / live-read indexes (telemetry + results)
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS stream_results_tenant_created_asc_idx
  ON public.stream_results (tenant_id, created_at ASC, id ASC);

CREATE INDEX IF NOT EXISTS telemetry_events_tenant_created_asc_idx
  ON public.telemetry_events (tenant_id, created_at ASC, id ASC);

CREATE INDEX IF NOT EXISTS embedding_vectors_tenant_anomaly_idx
  ON public.embedding_vectors (tenant_id, is_anomaly, created_at DESC)
  WHERE is_anomaly = TRUE;

-- ---------------------------------------------------------------------------
-- Consumer feed view (metadata scores only — no ciphertext columns)
-- RLS: security_invoker so underlying stream_results policies apply.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW public.projection_feed
  WITH (security_invoker = true)
AS
SELECT
  id,
  tenant_id,
  telemetry_event_id,
  source_event_id,
  created_at,
  kind,
  engine,
  score,
  is_anomaly,
  features,
  metadata,
  workflow_id,
  projection_name,
  projection_version
FROM public.stream_results;

GRANT SELECT ON public.projection_feed TO authenticated;
GRANT ALL ON public.projection_feed TO service_role;

COMMENT ON VIEW public.projection_feed IS
  'Consumer-safe live projections (scores/rollups). Prefer over raw stream_results in Realtime clients.';

-- ---------------------------------------------------------------------------
-- Supabase Realtime publication (no-op when publication is absent)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    IF NOT EXISTS (
      SELECT 1
      FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = 'stream_results'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE public.stream_results;
    END IF;

    -- Optional: sealed event *rows* for clients that decrypt locally.
    -- Ciphertext is still E2EE; do not subscribe if the UI only needs scores.
    IF NOT EXISTS (
      SELECT 1
      FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime'
        AND schemaname = 'public'
        AND tablename = 'telemetry_events'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE public.telemetry_events;
    END IF;
  END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Service-account default scopes (new rows; existing rows unchanged)
-- ---------------------------------------------------------------------------
ALTER TABLE public.service_accounts
  ALTER COLUMN scopes SET DEFAULT ARRAY[
    'ingest:write',
    'ingest:read',
    'projections:read',
    'projections:run',
    'sessions:write',
    'sessions:read'
  ]::text[];
