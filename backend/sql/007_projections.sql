-- =============================================================================
-- FORJD durable projections + checkpoints + DLQ (universal SaaS)
-- =============================================================================
-- Apply after 006. Metadata-only projections — never store plaintext/ciphertext.
-- Checkpointed projectors + DLQ via Rust/Python processors + Postgres.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Durable projection identity on stream_results
-- ---------------------------------------------------------------------------
ALTER TABLE public.stream_results
  ADD COLUMN IF NOT EXISTS projection_name TEXT;

ALTER TABLE public.stream_results
  ADD COLUMN IF NOT EXISTS source_event_id UUID;

ALTER TABLE public.stream_results
  ADD COLUMN IF NOT EXISTS projection_version INT NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS stream_results_tenant_proj_idx
  ON public.stream_results (tenant_id, projection_name, created_at DESC);

-- Idempotent upserts when a row is tied to a source sealed event.
CREATE UNIQUE INDEX IF NOT EXISTS stream_results_proj_idem_uidx
  ON public.stream_results (tenant_id, projection_name, source_event_id)
  WHERE source_event_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Checkpoints (watermark per tenant + projection + workflow)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.projection_checkpoints (
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  projection_name TEXT NOT NULL,
  workflow_id TEXT NOT NULL DEFAULT '',
  last_event_id UUID,
  last_created_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, projection_name, workflow_id)
);

ALTER TABLE public.projection_checkpoints ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS proj_ckpt_select_member ON public.projection_checkpoints;
CREATE POLICY proj_ckpt_select_member ON public.projection_checkpoints
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS proj_ckpt_service_all ON public.projection_checkpoints;
CREATE POLICY proj_ckpt_service_all ON public.projection_checkpoints
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT ON public.projection_checkpoints TO authenticated;
GRANT ALL ON public.projection_checkpoints TO service_role;

-- ---------------------------------------------------------------------------
-- Projection DLQ (metadata + error only — never ciphertext)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.projection_dlq (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  source_event_id UUID,
  workflow_id TEXT,
  projection_name TEXT NOT NULL,
  error TEXT NOT NULL,
  payload_meta JSONB NOT NULL DEFAULT '{}'::jsonb,
  attempts INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS projection_dlq_tenant_open_idx
  ON public.projection_dlq (tenant_id, created_at DESC)
  WHERE resolved_at IS NULL;

ALTER TABLE public.projection_dlq ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS proj_dlq_select_member ON public.projection_dlq;
CREATE POLICY proj_dlq_select_member ON public.projection_dlq
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS proj_dlq_service_all ON public.projection_dlq;
CREATE POLICY proj_dlq_service_all ON public.projection_dlq
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT ON public.projection_dlq TO authenticated;
GRANT ALL ON public.projection_dlq TO service_role;
