-- =============================================================================
-- FORJD Rust data-plane tables (daemon outbox, scheduler, probes, normalizer)
-- =============================================================================
-- Apply after 008. Durable data plane for forjd-daemon:
--   Postgres outbox + LISTEN/NOTIFY, Dragonfly Streams bus, FORJD tenants.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Transactional outbox (relay → Dragonfly Streams)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.outbox_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic TEXT NOT NULL,
  key TEXT,
  payload JSONB NOT NULL,
  headers JSONB NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key TEXT UNIQUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  attempts INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 5,
  is_published BOOLEAN NOT NULL DEFAULT FALSE,
  published_at TIMESTAMPTZ,
  last_error TEXT,
  dlq_at TIMESTAMPTZ,
  lease_owner UUID,
  lease_expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS outbox_events_claim_idx
  ON public.outbox_events (available_at, created_at)
  WHERE is_published = FALSE AND dlq_at IS NULL;

CREATE OR REPLACE FUNCTION public.notify_outbox_events()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  PERFORM pg_notify('forjd_outbox', NEW.id::text);
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS outbox_events_notify ON public.outbox_events;
CREATE TRIGGER outbox_events_notify
  AFTER INSERT ON public.outbox_events
  FOR EACH ROW
  EXECUTE FUNCTION public.notify_outbox_events();

ALTER TABLE public.outbox_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS outbox_events_service_all ON public.outbox_events;
CREATE POLICY outbox_events_service_all ON public.outbox_events
  FOR ALL TO service_role USING (true) WITH CHECK (true);
GRANT ALL ON public.outbox_events TO service_role;

-- ---------------------------------------------------------------------------
-- Durable scheduler buckets (role=scheduler)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.scheduled_task_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  task_name TEXT NOT NULL,
  scheduled_for TIMESTAMPTZ NOT NULL,
  state TEXT NOT NULL DEFAULT 'pending'
    CHECK (state IN ('pending', 'running', 'published', 'completed', 'failed')),
  attempts INT NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  claimed_by UUID,
  lease_expires_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (task_name, scheduled_for)
);

CREATE INDEX IF NOT EXISTS scheduled_task_runs_claim_idx
  ON public.scheduled_task_runs (scheduled_for, state);

ALTER TABLE public.scheduled_task_runs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS scheduled_task_runs_service_all ON public.scheduled_task_runs;
CREATE POLICY scheduled_task_runs_service_all ON public.scheduled_task_runs
  FOR ALL TO service_role USING (true) WITH CHECK (true);
GRANT ALL ON public.scheduled_task_runs TO service_role;

-- ---------------------------------------------------------------------------
-- Daemon ingest API keys (tenant-scoped; SHA-256 of full token)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.daemon_api_keys (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  prefix TEXT NOT NULL,
  key_hash TEXT NOT NULL,
  tier TEXT NOT NULL DEFAULT 'standard',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (prefix)
);

CREATE INDEX IF NOT EXISTS daemon_api_keys_tenant_idx
  ON public.daemon_api_keys (tenant_id);

ALTER TABLE public.daemon_api_keys ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS daemon_api_keys_service_all ON public.daemon_api_keys;
CREATE POLICY daemon_api_keys_service_all ON public.daemon_api_keys
  FOR ALL TO service_role USING (true) WITH CHECK (true);
GRANT ALL ON public.daemon_api_keys TO service_role;

-- ---------------------------------------------------------------------------
-- Normalizer receipts + endpoint observations (Dragonfly stream offsets)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.telemetry_ingest_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  stream TEXT NOT NULL,
  message_id TEXT NOT NULL,
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  event_id TEXT NOT NULL,
  processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (stream, message_id)
);

CREATE TABLE IF NOT EXISTS public.endpoint_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  status_code INT NOT NULL,
  response_time_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
  ip_address INET,
  device_type TEXT NOT NULL DEFAULT 'Unknown',
  os_name TEXT NOT NULL DEFAULT 'Unknown',
  browser_name TEXT NOT NULL DEFAULT 'Unknown',
  is_bot BOOLEAN NOT NULL DEFAULT FALSE,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  telemetry_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS endpoint_observations_tenant_idx
  ON public.endpoint_observations (tenant_id, observed_at DESC);

ALTER TABLE public.telemetry_ingest_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.endpoint_observations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS telemetry_ingest_receipts_service_all ON public.telemetry_ingest_receipts;
CREATE POLICY telemetry_ingest_receipts_service_all ON public.telemetry_ingest_receipts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS endpoint_observations_service_all ON public.endpoint_observations;
CREATE POLICY endpoint_observations_service_all ON public.endpoint_observations
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS endpoint_observations_select_member ON public.endpoint_observations;
CREATE POLICY endpoint_observations_select_member ON public.endpoint_observations
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

GRANT ALL ON public.telemetry_ingest_receipts, public.endpoint_observations TO service_role;
GRANT SELECT ON public.endpoint_observations TO authenticated;

-- ---------------------------------------------------------------------------
-- Probe observations + optional probe URL on status services
-- ---------------------------------------------------------------------------
ALTER TABLE public.status_services
  ADD COLUMN IF NOT EXISTS probe_url TEXT;

CREATE TABLE IF NOT EXISTS public.health_probe_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  observation_key TEXT NOT NULL UNIQUE,
  service_id UUID NOT NULL REFERENCES public.status_services (id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  status_code INT NOT NULL,
  response_time_ms BIGINT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT FALSE,
  error TEXT NOT NULL DEFAULT '',
  observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS health_probe_observations_tenant_idx
  ON public.health_probe_observations (tenant_id, observed_at DESC);

ALTER TABLE public.health_probe_observations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS health_probe_observations_service_all ON public.health_probe_observations;
CREATE POLICY health_probe_observations_service_all ON public.health_probe_observations
  FOR ALL TO service_role USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS health_probe_observations_select_member ON public.health_probe_observations;
CREATE POLICY health_probe_observations_select_member ON public.health_probe_observations
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
GRANT ALL ON public.health_probe_observations TO service_role;
GRANT SELECT ON public.health_probe_observations TO authenticated;
