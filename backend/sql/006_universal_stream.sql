-- =============================================================================
-- FORJD universal stream extensions (multi use-case SaaS)
-- =============================================================================
-- Apply after 003–005. Additive only — does not rename telemetry_events.
--
-- Goals:
--   • event_type / workflow_id for configurable routing
--   • use_cases catalog (mirror of YAML workflows for UI / SaaS discovery)
--   • sealed_events view alias (universal naming without breaking FKs)
--   • stream_results.workflow_id for consumer filtering
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Sealed events: flexible type + workflow routing
-- ---------------------------------------------------------------------------
ALTER TABLE public.telemetry_events
  ADD COLUMN IF NOT EXISTS event_type TEXT;

ALTER TABLE public.telemetry_events
  ADD COLUMN IF NOT EXISTS workflow_id TEXT;

-- Universal default content_type (overrides older telemetry-flavored default).
ALTER TABLE public.telemetry_events
  ALTER COLUMN content_type SET DEFAULT 'application/forjd-event+v1';

CREATE INDEX IF NOT EXISTS telemetry_events_tenant_type_idx
  ON public.telemetry_events (tenant_id, content_type, event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_events_tenant_workflow_idx
  ON public.telemetry_events (tenant_id, workflow_id, created_at DESC);

-- Universal alias — same rows; prefer this name in new docs/clients.
CREATE OR REPLACE VIEW public.sealed_events AS
  SELECT * FROM public.telemetry_events;

GRANT SELECT ON public.sealed_events TO authenticated;
GRANT ALL ON public.sealed_events TO service_role;

-- ---------------------------------------------------------------------------
-- Stream results: workflow tag for multi-product consumers
-- ---------------------------------------------------------------------------
ALTER TABLE public.stream_results
  ADD COLUMN IF NOT EXISTS workflow_id TEXT;

CREATE INDEX IF NOT EXISTS stream_results_tenant_workflow_idx
  ON public.stream_results (tenant_id, workflow_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Use-case catalog (optional DB mirror of backend/workflows/*.yaml)
-- Service role upserts; members can read enabled rows.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.use_cases (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  content_types TEXT[] NOT NULL DEFAULT '{}',
  event_types TEXT[] NOT NULL DEFAULT '{}',
  config JSONB NOT NULL DEFAULT '{}'::jsonb,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.use_cases ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS use_cases_select_authenticated ON public.use_cases;
CREATE POLICY use_cases_select_authenticated ON public.use_cases
  FOR SELECT TO authenticated
  USING (enabled = TRUE);

DROP POLICY IF EXISTS use_cases_service_all ON public.use_cases;
CREATE POLICY use_cases_service_all ON public.use_cases
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT ON public.use_cases TO authenticated;
GRANT ALL ON public.use_cases TO service_role;
