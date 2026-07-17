-- =============================================================================
-- Audit log + daemon rate-limit column (secure-by-default ops surface)
-- =============================================================================
-- Apply after 009. Metadata-only audit trail; never store ciphertext / keys.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Append-only audit events (service_role write; members read own tenant)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  actor_user_id TEXT,
  tenant_id UUID REFERENCES public.tenants (id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL DEFAULT '',
  resource_id TEXT NOT NULL DEFAULT '',
  details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS audit_events_tenant_created_idx
  ON public.audit_events (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS audit_events_action_created_idx
  ON public.audit_events (action, created_at DESC);

ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_events_service_all ON public.audit_events;
CREATE POLICY audit_events_service_all ON public.audit_events
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS audit_events_select_member ON public.audit_events;
CREATE POLICY audit_events_select_member ON public.audit_events
  FOR SELECT TO authenticated
  USING (
    tenant_id IS NOT NULL
    AND public.is_tenant_member(tenant_id)
  );

GRANT ALL ON public.audit_events TO service_role;
GRANT SELECT ON public.audit_events TO authenticated;

-- ---------------------------------------------------------------------------
-- Config-driven daemon ingest rate limits (replaces hardcoded Pro tier)
-- ---------------------------------------------------------------------------
ALTER TABLE public.daemon_api_keys
  ADD COLUMN IF NOT EXISTS rate_limit_rpm INT NOT NULL DEFAULT 60;

COMMENT ON COLUMN public.daemon_api_keys.rate_limit_rpm IS
  'Requests per minute for edge ingest; tier is advisory only.';

COMMENT ON COLUMN public.daemon_api_keys.tier IS
  'Advisory label (standard/pro/enterprise); rate_limit_rpm is authoritative.';
