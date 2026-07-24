-- =============================================================================
-- FORJD stream processing results (processors → Supabase; consumer-readable)
-- =============================================================================
-- Apply after 003_secure_tenancy.sql.
--
-- Threat model:
--   • Results are derived from server-visible metadata only (sizes, counts, key_id).
--   • Never store plaintext or ciphertext here — consumers read scores/rollups.
--   • RLS mirrors telemetry_events: tenant members read; service_role writes.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Rust / Python / Prefect outputs for downstream consumers (dashboards, SaaS apps)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.stream_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  -- Optional link to the sealed event that triggered this row (null for aggregates).
  telemetry_event_id UUID REFERENCES public.telemetry_events (id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- rollup | anomaly | transform
  kind TEXT NOT NULL DEFAULT 'rollup'
    CHECK (kind IN ('rollup', 'anomaly', 'transform')),
  engine TEXT NOT NULL DEFAULT 'pathway',
  -- Higher = more anomalous for kind=anomaly; unused/null for pure rollups.
  score DOUBLE PRECISION,
  is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
  -- Non-sensitive features only (cipher_len, z_score, counts, key_id, …).
  features JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS stream_results_tenant_created_idx
  ON public.stream_results (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS stream_results_tenant_anomaly_idx
  ON public.stream_results (tenant_id, is_anomaly, created_at DESC)
  WHERE is_anomaly = TRUE;

ALTER TABLE public.stream_results REPLICA IDENTITY FULL;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.stream_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS stream_results_select_member ON public.stream_results;
CREATE POLICY stream_results_select_member ON public.stream_results
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

-- Members do not insert directly — Prefect/API (service_role) writes results.
DROP POLICY IF EXISTS stream_results_service_all ON public.stream_results;
CREATE POLICY stream_results_service_all ON public.stream_results
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- Grants
-- ---------------------------------------------------------------------------
GRANT SELECT ON public.stream_results TO authenticated;
GRANT ALL ON public.stream_results TO service_role;

-- Optional Realtime for UI / consumers:
-- ALTER PUBLICATION supabase_realtime ADD TABLE public.stream_results;
