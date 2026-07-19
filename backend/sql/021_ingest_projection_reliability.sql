-- =============================================================================
-- Reliable sealed ingest, deterministic projections, replay/DLQ, tenant erase
-- =============================================================================
-- Apply after 020_headless_siem_soar.sql.
-- Additive state used to make retries deterministic and crash-safe. No plaintext
-- is introduced: byte counts, hashes, routing identities, and error metadata only.
-- =============================================================================

-- Canonical ciphertext size and immutable request identity. New writes populate
-- ingest_fingerprint; legacy rows remain nullable and are verified field-by-field
-- on their first duplicate request.
ALTER TABLE public.telemetry_events
  ADD COLUMN IF NOT EXISTS ciphertext_bytes INT;

UPDATE public.telemetry_events
SET ciphertext_bytes = octet_length(decode(ciphertext, 'base64'))
WHERE ciphertext_bytes IS NULL;

ALTER TABLE public.telemetry_events
  ALTER COLUMN ciphertext_bytes SET NOT NULL;

ALTER TABLE public.telemetry_events
  ADD COLUMN IF NOT EXISTS ingest_fingerprint TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'telemetry_events_ciphertext_bytes_nonnegative'
      AND conrelid = 'public.telemetry_events'::regclass
  ) THEN
    ALTER TABLE public.telemetry_events
      ADD CONSTRAINT telemetry_events_ciphertext_bytes_nonnegative
      CHECK (ciphertext_bytes >= 0);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'telemetry_events_ingest_fingerprint_shape'
      AND conrelid = 'public.telemetry_events'::regclass
  ) THEN
    ALTER TABLE public.telemetry_events
      ADD CONSTRAINT telemetry_events_ingest_fingerprint_shape
      CHECK (ingest_fingerprint IS NULL OR ingest_fingerprint ~ '^[0-9a-f]{64}$');
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS telemetry_events_projector_cursor_idx
  ON public.telemetry_events (tenant_id, workflow_id, created_at, id);

-- One durable row per projection/version/result identity. The result key hashes
-- source event + detector, or the exact aggregate input event set.
ALTER TABLE public.stream_results
  ADD COLUMN IF NOT EXISTS projection_result_key TEXT;

UPDATE public.stream_results
SET projection_name = COALESCE(
  NULLIF(projection_name, ''),
  NULLIF(metadata ->> 'projection_name', ''),
  'sealed.default'
)
WHERE projection_name IS NULL OR projection_name = '';

ALTER TABLE public.stream_results
  ALTER COLUMN projection_name SET NOT NULL;

UPDATE public.stream_results
SET projection_result_key = encode(digest(id::text, 'sha256'), 'hex')
WHERE projection_result_key IS NULL;

ALTER TABLE public.stream_results
  ALTER COLUMN projection_result_key SET NOT NULL;

DROP INDEX IF EXISTS public.stream_results_proj_idem_uidx;

CREATE UNIQUE INDEX IF NOT EXISTS stream_results_projection_result_uidx
  ON public.stream_results (
    tenant_id, projection_name, projection_version, projection_result_key
  );

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'stream_results_projection_result_key_shape'
      AND conrelid = 'public.stream_results'::regclass
  ) THEN
    ALTER TABLE public.stream_results
      ADD CONSTRAINT stream_results_projection_result_key_shape
      CHECK (projection_result_key ~ '^[0-9a-f]{64}$');
  END IF;
END $$;

-- DLQ attempt scheduling and exclusive retry leases.
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS dedupe_key TEXT;
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS projection_version INT NOT NULL DEFAULT 1;
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS error_class TEXT NOT NULL DEFAULT 'processing_error';
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS max_attempts INT NOT NULL DEFAULT 10;
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS last_attempt_at TIMESTAMPTZ;
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ;
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS locked_by TEXT;
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ;
ALTER TABLE public.projection_dlq
  ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE public.projection_dlq
SET dedupe_key = encode(digest(id::text, 'sha256'), 'hex')
WHERE dedupe_key IS NULL;

ALTER TABLE public.projection_dlq
  ALTER COLUMN dedupe_key SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS projection_dlq_open_dedupe_uidx
  ON public.projection_dlq (tenant_id, dedupe_key)
  WHERE resolved_at IS NULL;

CREATE INDEX IF NOT EXISTS projection_dlq_retry_ready_idx
  ON public.projection_dlq (next_attempt_at, created_at)
  WHERE resolved_at IS NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'projection_dlq_attempt_bounds'
      AND conrelid = 'public.projection_dlq'::regclass
  ) THEN
    ALTER TABLE public.projection_dlq
      ADD CONSTRAINT projection_dlq_attempt_bounds
      CHECK (attempts >= 0 AND max_attempts BETWEEN 1 AND 100);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'projection_dlq_projection_version_positive'
      AND conrelid = 'public.projection_dlq'::regclass
  ) THEN
    ALTER TABLE public.projection_dlq
      ADD CONSTRAINT projection_dlq_projection_version_positive
      CHECK (projection_version >= 1);
  END IF;
END $$;

-- Receipt intentionally has no tenant FK: it must survive tenant deletion and
-- make a retried account-deletion request idempotent.
CREATE TABLE IF NOT EXISTS public.tenant_erase_receipts (
  tenant_id UUID PRIMARY KEY,
  requested_by TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'completed')),
  deleted_counts JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- Tombstone for a lost response after this credential is deleted. These are
  -- lookup/hash-verification fields only; the raw opaque token is never stored.
  erased_credential_prefix TEXT,
  erased_credential_hash TEXT,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.tenant_erase_receipts
  ADD COLUMN IF NOT EXISTS erased_credential_prefix TEXT;
ALTER TABLE public.tenant_erase_receipts
  ADD COLUMN IF NOT EXISTS erased_credential_hash TEXT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'tenant_erase_receipts_credential_tombstone_shape'
      AND conrelid = 'public.tenant_erase_receipts'::regclass
  ) THEN
    ALTER TABLE public.tenant_erase_receipts
      ADD CONSTRAINT tenant_erase_receipts_credential_tombstone_shape
      CHECK (
        (erased_credential_prefix IS NULL AND erased_credential_hash IS NULL)
        OR (
          erased_credential_prefix IS NOT NULL
          AND erased_credential_hash IS NOT NULL
          AND char_length(erased_credential_prefix) = 8
          AND erased_credential_hash ~ '^[0-9a-f]{64}$'
        )
      );
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS tenant_erase_receipts_credential_hash_uidx
  ON public.tenant_erase_receipts (erased_credential_hash)
  WHERE erased_credential_hash IS NOT NULL;

ALTER TABLE public.tenant_erase_receipts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_erase_receipts_service_all
  ON public.tenant_erase_receipts;
CREATE POLICY tenant_erase_receipts_service_all ON public.tenant_erase_receipts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT ALL ON public.tenant_erase_receipts TO service_role;

COMMENT ON COLUMN public.telemetry_events.ciphertext_bytes IS
  'Validated decoded ciphertext byte count; canonical across live processing and replay.';
COMMENT ON COLUMN public.telemetry_events.ingest_fingerprint IS
  'SHA-256 over immutable routing and encryption metadata for idempotency conflicts.';
COMMENT ON COLUMN public.stream_results.projection_result_key IS
  'Deterministic SHA-256 identity for source detector or aggregate input set.';
COMMENT ON COLUMN public.projection_dlq.projection_version IS
  'Exact projection contract version for the isolated replay lane; retries fail closed on version drift.';
COMMENT ON TABLE public.tenant_erase_receipts IS
  'Durable idempotency receipt retained after a tenant and all tenant data are erased.';
COMMENT ON COLUMN public.tenant_erase_receipts.erased_credential_hash IS
  'SHA-256 tombstone of the authenticated opaque erase credential; valid only for same-tenant completed receipt replay.';
