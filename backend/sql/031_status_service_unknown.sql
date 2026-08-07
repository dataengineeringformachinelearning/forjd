-- =============================================================================
-- Status services — allow honest ``unknown`` (never invent operational)
-- =============================================================================
-- Apply after 030. New services default to ``unknown`` until a probe or an
-- explicit operator write sets a concrete health enum. Explore/directory cards
-- derive overall_status from these rows — green must not be the empty default.
-- =============================================================================

ALTER TABLE public.status_services
  DROP CONSTRAINT IF EXISTS status_services_status_check;

ALTER TABLE public.status_services
  ADD CONSTRAINT status_services_status_check
  CHECK (status IN (
    'operational',
    'degraded',
    'partial_outage',
    'major_outage',
    'maintenance',
    'unknown'
  ));

ALTER TABLE public.status_services
  ALTER COLUMN status SET DEFAULT 'unknown';
