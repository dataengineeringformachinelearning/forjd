-- Durable, idempotent export jobs with replica-safe worker leases and expiry.
-- Apply after 022_report_documents.sql.

ALTER TABLE public.export_jobs
  ADD COLUMN IF NOT EXISTS idempotency_key TEXT,
  ADD COLUMN IF NOT EXISTS request_fingerprint TEXT,
  ADD COLUMN IF NOT EXISTS filters JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS byte_size BIGINT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  ADD COLUMN IF NOT EXISTS attempts INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT 5,
  ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ADD COLUMN IF NOT EXISTS lease_owner UUID,
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

-- SQL/011 allowed only pending/running/completed/failed. Drop legacy checks
-- before writing any of the durable worker states introduced here.
ALTER TABLE public.export_jobs DROP CONSTRAINT IF EXISTS export_jobs_status_check;
ALTER TABLE public.export_jobs DROP CONSTRAINT IF EXISTS export_jobs_format_check;
ALTER TABLE public.export_jobs DROP CONSTRAINT IF EXISTS export_jobs_source_kind_check;
ALTER TABLE public.export_jobs DROP CONSTRAINT IF EXISTS export_jobs_attempts_bounds;
ALTER TABLE public.export_jobs DROP CONSTRAINT IF EXISTS export_jobs_artifact_metadata;
ALTER TABLE public.export_jobs DROP CONSTRAINT IF EXISTS export_jobs_lease_shape;

UPDATE public.export_jobs
SET idempotency_key = COALESCE(idempotency_key, 'legacy:' || id::text),
    request_fingerprint = COALESCE(
      request_fingerprint,
      encode(digest(format || ':' || source_kind, 'sha256'), 'hex')
    ),
    content_type = CASE format
      WHEN 'csv' THEN 'text/csv; charset=utf-8'
      WHEN 'json' THEN 'application/json'
      WHEN 'parquet' THEN 'application/vnd.apache.parquet'
      ELSE 'application/octet-stream'
    END,
    -- A pre-migration running process has no durable lease. Requeue it instead
    -- of leaving an unrecoverable status='running'/NULL-lease row.
    status = CASE
      WHEN status = 'pending'
        OR (status = 'running' AND (lease_owner IS NULL OR lease_expires_at IS NULL))
      THEN 'queued'
      ELSE status
    END,
    lease_owner = CASE
      WHEN status = 'pending'
        OR (status = 'running' AND (lease_owner IS NULL OR lease_expires_at IS NULL))
      THEN NULL
      ELSE lease_owner
    END,
    lease_expires_at = CASE
      WHEN status = 'pending'
        OR (status = 'running' AND (lease_owner IS NULL OR lease_expires_at IS NULL))
      THEN NULL
      ELSE lease_expires_at
    END,
    next_attempt_at = CASE
      WHEN status = 'pending'
        OR (status = 'running' AND (lease_owner IS NULL OR lease_expires_at IS NULL))
      THEN NOW()
      ELSE next_attempt_at
    END,
    expires_at = CASE
      WHEN status = 'completed' THEN COALESCE(expires_at, completed_at + INTERVAL '7 days')
      ELSE expires_at
    END;

UPDATE public.export_jobs
SET filters = filters || jsonb_build_object('legacy_source_kind', source_kind),
    source_kind = 'stream_results',
    status = 'failed',
    error = COALESCE(error, 'LegacyUnsupportedSourceKind'),
    completed_at = COALESCE(completed_at, NOW())
WHERE source_kind NOT IN (
  'stream_results', 'analytics', 'threat', 'lighthouse', 'vulnerabilities'
);

ALTER TABLE public.export_jobs
  ALTER COLUMN idempotency_key SET NOT NULL,
  ALTER COLUMN request_fingerprint SET NOT NULL;

ALTER TABLE public.export_jobs
  ADD CONSTRAINT export_jobs_format_check CHECK (
    format IN ('csv', 'json', 'parquet', 'pdf')
  );
ALTER TABLE public.export_jobs
  ADD CONSTRAINT export_jobs_status_check CHECK (
    status IN ('queued', 'running', 'retry_scheduled', 'completed', 'failed', 'expired')
  );
ALTER TABLE public.export_jobs
  ADD CONSTRAINT export_jobs_source_kind_check CHECK (
    source_kind IN ('stream_results', 'analytics', 'threat', 'lighthouse', 'vulnerabilities')
  );
ALTER TABLE public.export_jobs
  ADD CONSTRAINT export_jobs_attempts_bounds CHECK (
    attempts >= 0 AND max_attempts BETWEEN 1 AND 20 AND attempts <= max_attempts
  ) NOT VALID;
ALTER TABLE public.export_jobs VALIDATE CONSTRAINT export_jobs_attempts_bounds;
ALTER TABLE public.export_jobs
  ADD CONSTRAINT export_jobs_artifact_metadata CHECK (
    byte_size >= 0
    AND (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$')
  ) NOT VALID;
ALTER TABLE public.export_jobs VALIDATE CONSTRAINT export_jobs_artifact_metadata;
ALTER TABLE public.export_jobs
  ADD CONSTRAINT export_jobs_lease_shape CHECK (
    (status = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)
  ) NOT VALID;
ALTER TABLE public.export_jobs VALIDATE CONSTRAINT export_jobs_lease_shape;

CREATE UNIQUE INDEX IF NOT EXISTS export_jobs_tenant_idempotency_idx
  ON public.export_jobs (tenant_id, idempotency_key);
CREATE INDEX IF NOT EXISTS export_jobs_worker_idx
  ON public.export_jobs (next_attempt_at, created_at, id)
  WHERE status IN ('queued', 'retry_scheduled');
CREATE INDEX IF NOT EXISTS export_jobs_expiry_idx
  ON public.export_jobs (expires_at, id)
  WHERE status = 'completed' AND object_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS export_jobs_artifact_cleanup_idx
  ON public.export_jobs (next_attempt_at, id)
  WHERE status = 'failed' AND object_key IS NOT NULL;

COMMENT ON TABLE public.export_jobs IS
  'Tenant-scoped durable export jobs; artifacts reside in private object storage and expire.';
