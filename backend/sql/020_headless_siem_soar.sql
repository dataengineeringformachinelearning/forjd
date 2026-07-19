-- =============================================================================
-- Headless SIEM/SOAR foundation: normalized signals + durable playbook runs
-- =============================================================================
-- Apply after 019_least_privilege_erase_scope.sql.
--
-- The security_signals lane is deliberately separate from telemetry_events:
-- telemetry_events remains sealed evidence, while security_signals contains a
-- strict, selectively disclosed, PII-minimized normalized projection suitable
-- for search, correlation, cases, and automation.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.security_signals (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  client_signal_id TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  source TEXT NOT NULL,
  category TEXT NOT NULL CHECK (category IN (
    'authentication', 'malware', 'network', 'data_loss', 'vulnerability',
    'cloud', 'endpoint', 'application', 'threat_intelligence', 'other'
  )),
  signal_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'medium'
    CHECK (severity IN ('informational', 'low', 'medium', 'high', 'critical')),
  title TEXT NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  confidence INT NOT NULL DEFAULT 50 CHECK (confidence BETWEEN 0 AND 100),
  observables JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by_actor_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT security_signals_client_id_len CHECK (
    char_length(client_signal_id) BETWEEN 1 AND 128
  ),
  CONSTRAINT security_signals_hash_shape CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT security_signals_source_len CHECK (char_length(source) BETWEEN 1 AND 128),
  CONSTRAINT security_signals_type_len CHECK (char_length(signal_type) BETWEEN 1 AND 128),
  CONSTRAINT security_signals_title_len CHECK (char_length(title) BETWEEN 1 AND 255),
  CONSTRAINT security_signals_summary_len CHECK (char_length(summary) <= 2048),
  CONSTRAINT security_signals_observables_array CHECK (
    jsonb_typeof(observables) = 'array' AND jsonb_array_length(observables) <= 32
  ),
  CONSTRAINT security_signals_metadata_object CHECK (jsonb_typeof(metadata) = 'object'),
  CONSTRAINT security_signals_no_raw_fields CHECK (
    NOT (metadata ?| ARRAY[
      'raw', 'raw_payload', 'ciphertext', 'plaintext', 'password', 'secret',
      'token', 'authorization', 'cookie', 'email', 'username'
    ])
  ),
  UNIQUE (tenant_id, client_signal_id)
);

CREATE INDEX IF NOT EXISTS security_signals_tenant_observed_idx
  ON public.security_signals (tenant_id, observed_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS security_signals_tenant_severity_idx
  ON public.security_signals (tenant_id, severity, observed_at DESC);
CREATE INDEX IF NOT EXISTS security_signals_tenant_category_idx
  ON public.security_signals (tenant_id, category, observed_at DESC);
CREATE INDEX IF NOT EXISTS security_signals_tenant_source_idx
  ON public.security_signals (tenant_id, source, observed_at DESC);

CREATE TABLE IF NOT EXISTS public.correlation_receipts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  idempotency_key TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'processing'
    CHECK (status IN ('processing', 'completed')),
  created_by_actor_id UUID,
  match_count INT NOT NULL DEFAULT 0 CHECK (match_count >= 0),
  case_id UUID REFERENCES public.incident_cases (id) ON DELETE SET NULL,
  playbook_run_count INT NOT NULL DEFAULT 0 CHECK (playbook_run_count >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT correlation_receipts_key_len CHECK (
    char_length(idempotency_key) BETWEEN 1 AND 128
  ),
  CONSTRAINT correlation_receipts_hash_shape CHECK (
    request_sha256 ~ '^[0-9a-f]{64}$'
  ),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS correlation_receipts_tenant_created_idx
  ON public.correlation_receipts (tenant_id, created_at DESC);

ALTER TABLE public.incident_cases
  ADD COLUMN IF NOT EXISTS source_signal_id UUID
  REFERENCES public.security_signals (id) ON DELETE SET NULL;

ALTER TABLE public.incident_cases
  ADD COLUMN IF NOT EXISTS source_correlation_id UUID
  REFERENCES public.correlation_receipts (id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS incident_cases_source_signal_uidx
  ON public.incident_cases (tenant_id, source_signal_id)
  WHERE source_signal_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS incident_cases_source_correlation_uidx
  ON public.incident_cases (tenant_id, source_correlation_id)
  WHERE source_correlation_id IS NOT NULL;

ALTER TABLE public.playbooks
  ADD COLUMN IF NOT EXISTS version INT NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS public.playbook_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  playbook_id UUID NOT NULL REFERENCES public.playbooks (id) ON DELETE CASCADE,
  playbook_version INT NOT NULL CHECK (playbook_version >= 1),
  source_signal_id UUID REFERENCES public.security_signals (id) ON DELETE SET NULL,
  idempotency_key TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  trigger_source TEXT NOT NULL DEFAULT 'manual'
    CHECK (trigger_source IN ('manual', 'security_signal', 'correlation', 'integration')),
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN (
      'running', 'retrying', 'awaiting_ack',
      'succeeded', 'partial', 'failed', 'unsupported'
    )),
  trigger_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  action_plan_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_by_actor_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT playbook_runs_idempotency_len CHECK (
    char_length(idempotency_key) BETWEEN 1 AND 128
  ),
  CONSTRAINT playbook_runs_request_hash_shape CHECK (request_sha256 ~ '^[0-9a-f]{64}$'),
  CONSTRAINT playbook_runs_context_object CHECK (jsonb_typeof(trigger_context) = 'object'),
  CONSTRAINT playbook_runs_action_plan_shape CHECK (
    jsonb_typeof(action_plan_snapshot) = 'array'
    AND jsonb_array_length(action_plan_snapshot) <= 50
  ),
  UNIQUE (tenant_id, idempotency_key)
);

CREATE INDEX IF NOT EXISTS playbook_runs_tenant_created_idx
  ON public.playbook_runs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS playbook_runs_playbook_created_idx
  ON public.playbook_runs (tenant_id, playbook_id, created_at DESC);
CREATE INDEX IF NOT EXISTS playbook_runs_signal_idx
  ON public.playbook_runs (tenant_id, source_signal_id)
  WHERE source_signal_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.playbook_action_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES public.playbook_runs (id) ON DELETE CASCADE,
  playbook_action_id UUID REFERENCES public.playbook_actions (id) ON DELETE SET NULL,
  action_plan_key TEXT NOT NULL,
  action_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'running'
    CHECK (status IN (
      'running', 'retry_scheduled', 'awaiting_ack',
      'succeeded', 'failed', 'unsupported'
    )),
  attempt INT NOT NULL DEFAULT 1,
  max_attempts INT NOT NULL DEFAULT 5,
  status_code INT,
  error_code TEXT,
  external_reference TEXT,
  configuration_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
  result_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  next_attempt_at TIMESTAMPTZ,
  last_attempt_at TIMESTAMPTZ,
  lease_owner TEXT,
  lease_expires_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT playbook_action_results_attempt_bounds CHECK (
    max_attempts BETWEEN 1 AND 10 AND attempt BETWEEN 1 AND max_attempts
  ),
  CONSTRAINT playbook_action_results_configuration_object CHECK (
    jsonb_typeof(configuration_snapshot) = 'object'
  ),
  CONSTRAINT playbook_action_results_metadata_object CHECK (
    jsonb_typeof(result_metadata) = 'object'
  ),
  CONSTRAINT playbook_action_results_retry_shape CHECK (
    (status <> 'retry_scheduled' OR (
      action_type = 'webhook' AND next_attempt_at IS NOT NULL
    ))
    AND ((lease_owner IS NULL) = (lease_expires_at IS NULL))
    AND (lease_owner IS NULL OR char_length(lease_owner) BETWEEN 1 AND 128)
  ),
  UNIQUE (run_id, playbook_action_id),
  UNIQUE (run_id, action_plan_key)
);

-- Keep 020 idempotent for development databases that created the first SOAR
-- shape through SOFT_MIGRATE_SCHEMA before applying the production migration.
ALTER TABLE public.playbook_action_results
  ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT 5;
ALTER TABLE public.playbook_action_results
  ADD COLUMN IF NOT EXISTS action_plan_key TEXT;
ALTER TABLE public.playbook_action_results
  ADD COLUMN IF NOT EXISTS configuration_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.playbook_action_results
  ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;
ALTER TABLE public.playbook_action_results
  ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;
ALTER TABLE public.playbook_action_results
  ADD COLUMN IF NOT EXISTS lease_owner TEXT;
ALTER TABLE public.playbook_action_results
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE public.playbook_runs
  ADD COLUMN IF NOT EXISTS action_plan_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE public.playbook_action_results
SET action_plan_key = COALESCE(playbook_action_id::text, id::text)
WHERE action_plan_key IS NULL;
ALTER TABLE public.playbook_action_results
  ALTER COLUMN action_plan_key SET NOT NULL;

UPDATE public.playbook_action_results AS result
SET configuration_snapshot = jsonb_strip_nulls(
  jsonb_build_object(
    'url', action.configuration -> 'url',
    'secret_ref', action.configuration -> 'secret_ref'
  )
)
FROM public.playbook_actions AS action
WHERE result.playbook_action_id = action.id
  AND result.action_type = 'webhook'
  AND result.configuration_snapshot = '{}'::jsonb;

ALTER TABLE public.playbook_runs
  DROP CONSTRAINT IF EXISTS playbook_runs_status_check;
ALTER TABLE public.playbook_action_results
  DROP CONSTRAINT IF EXISTS playbook_action_results_status_check;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'playbook_runs_status_allowed'
      AND conrelid = 'public.playbook_runs'::regclass
  ) THEN
    ALTER TABLE public.playbook_runs
      ADD CONSTRAINT playbook_runs_status_allowed CHECK (status IN (
        'running', 'retrying', 'awaiting_ack',
        'succeeded', 'partial', 'failed', 'unsupported'
      ));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'playbook_runs_action_plan_shape'
      AND conrelid = 'public.playbook_runs'::regclass
  ) THEN
    ALTER TABLE public.playbook_runs
      ADD CONSTRAINT playbook_runs_action_plan_shape CHECK (
        jsonb_typeof(action_plan_snapshot) = 'array'
        AND jsonb_array_length(action_plan_snapshot) <= 50
      );
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'playbook_action_results_status_allowed'
      AND conrelid = 'public.playbook_action_results'::regclass
  ) THEN
    ALTER TABLE public.playbook_action_results
      ADD CONSTRAINT playbook_action_results_status_allowed CHECK (status IN (
        'running', 'retry_scheduled', 'awaiting_ack',
        'succeeded', 'failed', 'unsupported'
      ));
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'playbook_action_results_attempt_bounds'
      AND conrelid = 'public.playbook_action_results'::regclass
  ) THEN
    ALTER TABLE public.playbook_action_results
      ADD CONSTRAINT playbook_action_results_attempt_bounds CHECK (
        max_attempts BETWEEN 1 AND 10 AND attempt BETWEEN 1 AND max_attempts
      );
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'playbook_action_results_configuration_object'
      AND conrelid = 'public.playbook_action_results'::regclass
  ) THEN
    ALTER TABLE public.playbook_action_results
      ADD CONSTRAINT playbook_action_results_configuration_object CHECK (
        jsonb_typeof(configuration_snapshot) = 'object'
      );
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'playbook_action_results_retry_shape'
      AND conrelid = 'public.playbook_action_results'::regclass
  ) THEN
    ALTER TABLE public.playbook_action_results
      ADD CONSTRAINT playbook_action_results_retry_shape CHECK (
        (status <> 'retry_scheduled' OR (
          action_type = 'webhook' AND next_attempt_at IS NOT NULL
        ))
        AND ((lease_owner IS NULL) = (lease_expires_at IS NULL))
        AND (lease_owner IS NULL OR char_length(lease_owner) BETWEEN 1 AND 128)
      );
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public.prevent_playbook_run_plan_change()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.action_plan_snapshot IS DISTINCT FROM OLD.action_plan_snapshot THEN
    RAISE EXCEPTION 'playbook run action plan is immutable';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS playbook_runs_immutable_plan ON public.playbook_runs;
CREATE TRIGGER playbook_runs_immutable_plan
  BEFORE UPDATE OF action_plan_snapshot ON public.playbook_runs
  FOR EACH ROW EXECUTE FUNCTION public.prevent_playbook_run_plan_change();

CREATE INDEX IF NOT EXISTS playbook_action_results_run_idx
  ON public.playbook_action_results (run_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS playbook_action_results_plan_key_uidx
  ON public.playbook_action_results (run_id, action_plan_key);
CREATE INDEX IF NOT EXISTS playbook_action_results_retry_ready_idx
  ON public.playbook_action_results (next_attempt_at, created_at, id)
  WHERE action_type = 'webhook' AND status = 'retry_scheduled';
CREATE INDEX IF NOT EXISTS playbook_action_results_expired_lease_idx
  ON public.playbook_action_results (lease_expires_at, id)
  WHERE action_type = 'webhook' AND status = 'running'
    AND lease_expires_at IS NOT NULL;

-- New service principals support DEML's SIEM/case/playbook surfaces by default.
-- Global feed administration and ML training remain human-only/opt-in.
ALTER TABLE public.service_accounts
  ALTER COLUMN scopes SET DEFAULT ARRAY[
    'ingest:write', 'ingest:read',
    'projections:read', 'projections:run',
    'sessions:write', 'sessions:read',
    'replay:read', 'replay:write',
    'status:read', 'status:write',
    'analytics:read',
    'exports:read', 'exports:write',
    'vulnerabilities:read', 'vulnerabilities:write',
    'integrations:write',
    'siem:read', 'siem:write',
    'cases:read', 'cases:write',
    'playbooks:read', 'playbooks:write', 'playbooks:execute',
    'threat-intel:read'
  ]::text[];

-- ---------------------------------------------------------------------------
-- RLS: tenant members read; FastAPI writes through service_role after explicit
-- principal/tenant/scope authorization.  Browser clients do not mutate these
-- tables directly.
-- ---------------------------------------------------------------------------
ALTER TABLE public.security_signals ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.correlation_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.playbook_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.playbook_action_results ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS security_signals_select_member ON public.security_signals;
CREATE POLICY security_signals_select_member ON public.security_signals
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS security_signals_service_all ON public.security_signals;
CREATE POLICY security_signals_service_all ON public.security_signals
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS correlation_receipts_select_member ON public.correlation_receipts;
CREATE POLICY correlation_receipts_select_member ON public.correlation_receipts
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS correlation_receipts_service_all ON public.correlation_receipts;
CREATE POLICY correlation_receipts_service_all ON public.correlation_receipts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS playbook_runs_select_member ON public.playbook_runs;
CREATE POLICY playbook_runs_select_member ON public.playbook_runs
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS playbook_runs_service_all ON public.playbook_runs;
CREATE POLICY playbook_runs_service_all ON public.playbook_runs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS playbook_action_results_select_member
  ON public.playbook_action_results;
CREATE POLICY playbook_action_results_select_member ON public.playbook_action_results
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.playbook_runs run
      WHERE run.id = playbook_action_results.run_id
        AND public.is_tenant_member(run.tenant_id)
    )
  );
DROP POLICY IF EXISTS playbook_action_results_service_all
  ON public.playbook_action_results;
CREATE POLICY playbook_action_results_service_all ON public.playbook_action_results
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT SELECT ON public.security_signals TO authenticated;
GRANT SELECT ON public.correlation_receipts TO authenticated;
GRANT SELECT ON public.playbook_runs TO authenticated;
GRANT SELECT ON public.playbook_action_results TO authenticated;
GRANT ALL ON public.security_signals TO service_role;
GRANT ALL ON public.correlation_receipts TO service_role;
GRANT ALL ON public.playbook_runs TO service_role;
GRANT ALL ON public.playbook_action_results TO service_role;

-- Privileged security automation must leave append-only evidence. The API uses
-- audit.record_required for these paths, and the database rejects mutation of
-- an existing receipt even for service_role callers.
-- Keep the opaque tenant UUID after tenant erasure instead of ON DELETE SET
-- NULL, which would mutate the append-only row and block erasure via trigger.
ALTER TABLE public.audit_events
  DROP CONSTRAINT IF EXISTS audit_events_tenant_id_fkey;

CREATE OR REPLACE FUNCTION public.prevent_audit_event_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END $$;

DROP TRIGGER IF EXISTS audit_events_append_only ON public.audit_events;
CREATE TRIGGER audit_events_append_only
  BEFORE UPDATE OR DELETE OR TRUNCATE ON public.audit_events
  FOR EACH STATEMENT EXECUTE FUNCTION public.prevent_audit_event_mutation();

REVOKE ALL ON public.audit_events FROM authenticated, service_role;
GRANT SELECT ON public.audit_events TO authenticated;
GRANT SELECT, INSERT ON public.audit_events TO service_role;

COMMENT ON TABLE public.security_signals IS
  'PII-minimized normalized SIEM signals; raw evidence remains sealed in telemetry_events.';
COMMENT ON TABLE public.correlation_receipts IS
  'Tenant/key/request-fingerprint receipts for whole-operation SIEM correlation idempotency.';
COMMENT ON TABLE public.playbook_runs IS
  'Durable tenant-scoped SOAR receipts with immutable ordered action plans.';
COMMENT ON TABLE public.playbook_action_results IS
  'Durable per-action state, bounded webhook retries, leases, and control-plane ACKs.';
