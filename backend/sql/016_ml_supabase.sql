-- =============================================================================
-- FORJD ML ↔ Supabase (tenant-scoped runs, scores, pgvector, Realtime)
-- =============================================================================
-- Apply after 015_realtime_and_consumer.sql.
--
-- Threat model:
--   • training_runs / ml_scores hold metrics + metadata only — never ciphertext.
--   • Latents land in embedding_vectors (pgvector + RLS from 003).
--   • FastAPI uses service_role after principal + tenant checks.
--   • Browser clients read via authenticated RLS (is_tenant_member).
-- =============================================================================

-- ---------------------------------------------------------------------------
-- training_runs: family + kind for the unified /api/v1/ml catalog
-- ---------------------------------------------------------------------------
ALTER TABLE public.training_runs
  ADD COLUMN IF NOT EXISTS family TEXT NOT NULL DEFAULT '';

ALTER TABLE public.training_runs
  ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'fit';

CREATE INDEX IF NOT EXISTS training_runs_tenant_family_idx
  ON public.training_runs (tenant_id, family, created_at DESC);

-- ---------------------------------------------------------------------------
-- ml_scores: inference / forecast outputs (metadata only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.ml_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  family TEXT NOT NULL,
  model_name TEXT NOT NULL DEFAULT '',
  score DOUBLE PRECISION,
  is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
  features JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ml_scores_tenant_created_idx
  ON public.ml_scores (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ml_scores_tenant_family_idx
  ON public.ml_scores (tenant_id, family, created_at DESC);

CREATE INDEX IF NOT EXISTS ml_scores_tenant_anomaly_idx
  ON public.ml_scores (tenant_id, is_anomaly, created_at DESC)
  WHERE is_anomaly = TRUE;

ALTER TABLE public.ml_scores ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ml_scores_select_member ON public.ml_scores;
CREATE POLICY ml_scores_select_member ON public.ml_scores
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS ml_scores_service_all ON public.ml_scores;
CREATE POLICY ml_scores_service_all ON public.ml_scores
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT ON public.ml_scores TO authenticated;
GRANT ALL ON public.ml_scores TO service_role;

ALTER TABLE public.ml_scores REPLICA IDENTITY FULL;
ALTER TABLE public.training_runs REPLICA IDENTITY FULL;

-- ---------------------------------------------------------------------------
-- Realtime (optional publication; no-op if absent)
-- ---------------------------------------------------------------------------
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'ml_scores'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE public.ml_scores;
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM pg_publication_tables
      WHERE pubname = 'supabase_realtime' AND schemaname = 'public' AND tablename = 'training_runs'
    ) THEN
      ALTER PUBLICATION supabase_realtime ADD TABLE public.training_runs;
    END IF;
  END IF;
END $$;
