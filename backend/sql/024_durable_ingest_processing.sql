-- Durable canonical ingest processing ledger and leased recovery worker.
-- Apply after 023_durable_exports.sql.

CREATE TABLE IF NOT EXISTS public.ingest_processing_batches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  acceptance_id UUID NOT NULL,
  group_ordinal INT NOT NULL,
  dedupe_key TEXT NOT NULL,
  requested_by TEXT NOT NULL,
  workflow_id TEXT NOT NULL,
  workflow_version INT NOT NULL,
  workflow_hash TEXT NOT NULL,
  workflow_snapshot JSONB NOT NULL,
  projection_name TEXT NOT NULL,
  projection_version INT NOT NULL,
  content_type TEXT NOT NULL,
  event_type TEXT,
  events JSONB NOT NULL,
  event_ids UUID[] NOT NULL,
  tenant_ids UUID[] NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 10,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_attempt_at TIMESTAMPTZ,
  lease_owner UUID,
  lease_expires_at TIMESTAMPTZ,
  error_class TEXT,
  error TEXT,
  result_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  CONSTRAINT ingest_processing_status_check CHECK (
    status IN ('queued', 'running', 'retry_scheduled', 'completed', 'failed')
  ),
  CONSTRAINT ingest_processing_attempt_bounds CHECK (
    attempts >= 0 AND max_attempts BETWEEN 1 AND 100 AND attempts <= max_attempts
  ),
  CONSTRAINT ingest_processing_version_bounds CHECK (
    workflow_version >= 1 AND projection_version >= 1 AND group_ordinal >= 0
  ),
  CONSTRAINT ingest_processing_hash_shapes CHECK (
    dedupe_key ~ '^[0-9a-f]{64}$' AND workflow_hash ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT ingest_processing_snapshot_shapes CHECK (
    jsonb_typeof(workflow_snapshot) = 'object'
    AND jsonb_typeof(events) = 'array'
    AND jsonb_array_length(events) BETWEEN 1 AND 25
    AND cardinality(event_ids) = jsonb_array_length(events)
    AND cardinality(tenant_ids) = 1
  ),
  CONSTRAINT ingest_processing_lease_shape CHECK (
    (status = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)
  ),
  CONSTRAINT ingest_processing_completion_shape CHECK (
    (status = 'completed' AND completed_at IS NOT NULL)
    OR (status <> 'completed' AND completed_at IS NULL)
  ),
  UNIQUE (acceptance_id, group_ordinal),
  UNIQUE (dedupe_key)
);

CREATE INDEX IF NOT EXISTS ingest_processing_worker_idx
  ON public.ingest_processing_batches (next_attempt_at, created_at, acceptance_id, group_ordinal)
  WHERE status IN ('queued', 'retry_scheduled');

CREATE INDEX IF NOT EXISTS ingest_processing_event_ids_gin_idx
  ON public.ingest_processing_batches USING GIN (event_ids);

-- CREATE TABLE IF NOT EXISTS does not replace a constraint on an existing
-- development table. Rebuild this named contract so every application of the
-- migration upgrades the former multi-tenant array allowance as well.
ALTER TABLE public.ingest_processing_batches
  DROP CONSTRAINT IF EXISTS ingest_processing_snapshot_shapes;
ALTER TABLE public.ingest_processing_batches
  ADD CONSTRAINT ingest_processing_snapshot_shapes CHECK (
    jsonb_typeof(workflow_snapshot) = 'object'
    AND jsonb_typeof(events) = 'array'
    AND jsonb_array_length(events) BETWEEN 1 AND 25
    AND cardinality(event_ids) = jsonb_array_length(events)
    AND cardinality(tenant_ids) = 1
  ) NOT VALID;
ALTER TABLE public.ingest_processing_batches
  VALIDATE CONSTRAINT ingest_processing_snapshot_shapes;

-- The array constraint alone cannot prove that the embedded metadata belongs
-- to that tenant. Enforce the equality in Postgres as the last line of defense
-- against a future caller bypassing the Python registration path.
CREATE OR REPLACE FUNCTION public.enforce_ingest_processing_tenant_integrity()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF cardinality(NEW.tenant_ids) IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'ingest processing batch must contain exactly one tenant';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(NEW.events) AS event_value
    WHERE event_value->>'tenant_id' IS DISTINCT FROM NEW.tenant_ids[1]::text
  ) THEN
    RAISE EXCEPTION 'ingest processing event tenant does not match batch tenant';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS ingest_processing_tenant_integrity
  ON public.ingest_processing_batches;
CREATE TRIGGER ingest_processing_tenant_integrity
  BEFORE INSERT OR UPDATE ON public.ingest_processing_batches
  FOR EACH ROW EXECUTE FUNCTION public.enforce_ingest_processing_tenant_integrity();

-- State, leases, errors, and result summaries are mutable. The exact accepted
-- group and its execution contract are not: recovery must never reinterpret a
-- receipt after workflow configuration or service code changes.
CREATE OR REPLACE FUNCTION public.prevent_ingest_processing_identity_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.acceptance_id IS DISTINCT FROM OLD.acceptance_id
     OR NEW.group_ordinal IS DISTINCT FROM OLD.group_ordinal
     OR NEW.dedupe_key IS DISTINCT FROM OLD.dedupe_key
     OR NEW.requested_by IS DISTINCT FROM OLD.requested_by
     OR NEW.workflow_id IS DISTINCT FROM OLD.workflow_id
     OR NEW.workflow_version IS DISTINCT FROM OLD.workflow_version
     OR NEW.workflow_hash IS DISTINCT FROM OLD.workflow_hash
     OR NEW.workflow_snapshot IS DISTINCT FROM OLD.workflow_snapshot
     OR NEW.projection_name IS DISTINCT FROM OLD.projection_name
     OR NEW.projection_version IS DISTINCT FROM OLD.projection_version
     OR NEW.content_type IS DISTINCT FROM OLD.content_type
     OR NEW.event_type IS DISTINCT FROM OLD.event_type
     OR NEW.events IS DISTINCT FROM OLD.events
     OR NEW.event_ids IS DISTINCT FROM OLD.event_ids
     OR NEW.tenant_ids IS DISTINCT FROM OLD.tenant_ids
     OR NEW.max_attempts IS DISTINCT FROM OLD.max_attempts THEN
    RAISE EXCEPTION 'ingest processing identity is immutable';
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS ingest_processing_identity_immutable
  ON public.ingest_processing_batches;
CREATE TRIGGER ingest_processing_identity_immutable
  BEFORE UPDATE ON public.ingest_processing_batches
  FOR EACH ROW EXECUTE FUNCTION public.prevent_ingest_processing_identity_mutation();

ALTER TABLE public.ingest_processing_batches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS ingest_processing_service_all
  ON public.ingest_processing_batches;
CREATE POLICY ingest_processing_service_all
  ON public.ingest_processing_batches
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT ALL ON public.ingest_processing_batches TO service_role;

COMMENT ON TABLE public.ingest_processing_batches IS
  'Ciphertext-free processing receipts created atomically with sealed-event acceptance and recovered by leased workers.';
COMMENT ON COLUMN public.ingest_processing_batches.workflow_snapshot IS
  'Exact validated workflow configuration used for deterministic recovery; integrity is bound by workflow_hash.';
COMMENT ON COLUMN public.ingest_processing_batches.events IS
  'Ordered sealed-event metadata only; never ciphertext, plaintext, tokens, or key material.';
