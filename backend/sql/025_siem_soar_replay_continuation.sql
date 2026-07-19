-- =============================================================================
-- SIEM/SOAR replay receipts and durable continuation recovery
-- =============================================================================
-- Apply after 024_durable_ingest_processing.sql.
--
-- Completed operation receipts retain the exact public result so an
-- idempotent replay never evaluates a newer correlation rule or playbook
-- version. The partial run index supports the SOAR continuation reconciler.
-- =============================================================================

ALTER TABLE public.security_signals
  ADD COLUMN IF NOT EXISTS processing_status TEXT NOT NULL DEFAULT 'processing';
ALTER TABLE public.security_signals
  ADD COLUMN IF NOT EXISTS processing_result JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE public.security_signals
  ADD COLUMN IF NOT EXISTS processing_completed_at TIMESTAMPTZ;

-- Signals accepted before this migration have already passed through the old
-- synchronous processing path. Mark them completed without replaying current
-- automation rules.
UPDATE public.security_signals
SET processing_status = 'completed',
    processing_result = '{}'::jsonb,
    processing_completed_at = COALESCE(processing_completed_at, created_at, NOW())
WHERE processing_status = 'processing';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'security_signals_processing_contract'
      AND conrelid = 'public.security_signals'::regclass
  ) THEN
    ALTER TABLE public.security_signals
      ADD CONSTRAINT security_signals_processing_contract CHECK (
        processing_status IN ('processing', 'completed')
        AND jsonb_typeof(processing_result) = 'object'
        AND (
          (processing_status = 'processing' AND processing_completed_at IS NULL)
          OR (processing_status = 'completed' AND processing_completed_at IS NOT NULL)
        )
      );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS security_signals_processing_idx
  ON public.security_signals (created_at, id)
  WHERE processing_status = 'processing';

ALTER TABLE public.correlation_receipts
  ADD COLUMN IF NOT EXISTS result_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'correlation_receipts_result_snapshot_object'
      AND conrelid = 'public.correlation_receipts'::regclass
  ) THEN
    ALTER TABLE public.correlation_receipts
      ADD CONSTRAINT correlation_receipts_result_snapshot_object CHECK (
        jsonb_typeof(result_snapshot) = 'object'
      );
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS playbook_runs_continuation_ready_idx
  ON public.playbook_runs (updated_at, id)
  WHERE status IN ('running', 'retrying', 'awaiting_ack');

COMMENT ON COLUMN public.security_signals.processing_result IS
  'Immutable public SIEM processing result returned for exact idempotent replays.';
COMMENT ON COLUMN public.correlation_receipts.result_snapshot IS
  'Immutable public correlation result returned for exact idempotent replays.';
