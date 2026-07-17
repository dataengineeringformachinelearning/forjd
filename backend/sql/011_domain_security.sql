-- =============================================================================
-- FORJD domain security (DEML data-plane extract) — tenant-scoped, no auth.User
-- =============================================================================
-- Apply after 010. Identity/billing stay in DEML Django; FORJD owns workload tables.
-- Opaque actor_id fields may hold Supabase user UUIDs without joining auth tables.
-- =============================================================================

-- --- Assets / vulnerabilities ---
CREATE TABLE IF NOT EXISTS public.assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  hostname TEXT NOT NULL,
  internal_ip INET,
  os_version TEXT,
  mac_address TEXT,
  environment TEXT NOT NULL DEFAULT 'production'
    CHECK (environment IN ('production', 'staging', 'development')),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS assets_tenant_idx
  ON public.assets (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.vulnerabilities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  asset_id UUID REFERENCES public.assets (id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'triage'
    CHECK (status IN ('triage', 'open', 'in_progress', 'resolved', 'false_positive')),
  severity TEXT NOT NULL DEFAULT 'medium'
    CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  impact INT NOT NULL DEFAULT 3 CHECK (impact BETWEEN 1 AND 5),
  likelihood INT NOT NULL DEFAULT 3 CHECK (likelihood BETWEEN 1 AND 5),
  cve_id TEXT,
  telemetry_context JSONB,
  created_by_actor_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS vulnerabilities_tenant_status_idx
  ON public.vulnerabilities (tenant_id, status, created_at DESC);

-- --- Threat intelligence (platform or tenant-scoped feeds) ---
CREATE TABLE IF NOT EXISTS public.threat_intelligence (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID REFERENCES public.tenants (id) ON DELETE CASCADE,
  is_platform BOOLEAN NOT NULL DEFAULT FALSE,
  source TEXT NOT NULL,
  ip_address INET,
  location TEXT,
  abuse_confidence_score INT NOT NULL DEFAULT 0,
  otx_pulses INT NOT NULL DEFAULT 0,
  is_malicious BOOLEAN NOT NULL DEFAULT FALSE,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT threat_intel_scope CHECK (
    (is_platform = TRUE AND tenant_id IS NULL)
    OR (is_platform = FALSE AND tenant_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS threat_intel_ip_idx
  ON public.threat_intelligence (ip_address)
  WHERE ip_address IS NOT NULL;

CREATE INDEX IF NOT EXISTS threat_intel_tenant_time_idx
  ON public.threat_intelligence (tenant_id, created_at DESC)
  WHERE tenant_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS threat_intel_platform_source_idx
  ON public.threat_intelligence (is_platform, source, created_at DESC)
  WHERE is_platform = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS threat_intel_platform_source_ip_uidx
  ON public.threat_intelligence (source, ip_address)
  WHERE is_platform = TRUE AND ip_address IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS threat_intel_tenant_source_ip_uidx
  ON public.threat_intelligence (tenant_id, source, ip_address)
  WHERE tenant_id IS NOT NULL AND ip_address IS NOT NULL;

-- --- SOC cases + playbooks ---
CREATE TABLE IF NOT EXISTS public.incident_cases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'investigating', 'mitigated', 'resolved', 'false_positive')),
  severity TEXT NOT NULL DEFAULT 'medium'
    CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  assigned_actor_id UUID,
  status_incident_id UUID REFERENCES public.status_incidents (id) ON DELETE SET NULL,
  correlation_rule_ids TEXT[] NOT NULL DEFAULT '{}',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by_actor_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS incident_cases_tenant_idx
  ON public.incident_cases (tenant_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS public.playbooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  trigger_conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS playbooks_tenant_idx
  ON public.playbooks (tenant_id, is_active);

CREATE TABLE IF NOT EXISTS public.playbook_actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  playbook_id UUID NOT NULL REFERENCES public.playbooks (id) ON DELETE CASCADE,
  action_type TEXT NOT NULL
    CHECK (action_type IN ('webhook', 'email_alert', 'block_ip', 'revoke_api_key')),
  configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
  sort_order INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS playbook_actions_playbook_idx
  ON public.playbook_actions (playbook_id, sort_order);

-- --- Analytics rollups + export jobs ---
CREATE TABLE IF NOT EXISTS public.aggregated_analytics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  bucket_start TIMESTAMPTZ NOT NULL,
  bucket_size TEXT NOT NULL DEFAULT '1h',
  total_requests BIGINT NOT NULL DEFAULT 0,
  avg_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
  p99_latency_ms DOUBLE PRECISION NOT NULL DEFAULT 0,
  error_rate_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
  threats_detected INT NOT NULL DEFAULT 0,
  active_incidents INT NOT NULL DEFAULT 0,
  unique_visitors INT NOT NULL DEFAULT 0,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, bucket_start, bucket_size)
);

CREATE INDEX IF NOT EXISTS aggregated_analytics_tenant_time_idx
  ON public.aggregated_analytics (tenant_id, bucket_start DESC);

CREATE TABLE IF NOT EXISTS public.export_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  format TEXT NOT NULL CHECK (format IN ('csv', 'json', 'parquet')),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  source_kind TEXT NOT NULL DEFAULT 'stream_results',
  object_key TEXT,
  checksum_sha256 TEXT,
  error TEXT,
  created_by_actor_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS export_jobs_tenant_idx
  ON public.export_jobs (tenant_id, created_at DESC);

-- --- ML training / threat reports (tenant-scoped; no Django User) ---
CREATE TABLE IF NOT EXISTS public.training_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  model_name TEXT NOT NULL,
  model_version TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'completed'
    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  artifact_path TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS training_runs_tenant_idx
  ON public.training_runs (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.threat_reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  score DOUBLE PRECISION NOT NULL DEFAULT 0,
  features JSONB NOT NULL DEFAULT '[]'::jsonb,
  summary TEXT NOT NULL DEFAULT '',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS threat_reports_tenant_idx
  ON public.threat_reports (tenant_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- RLS (members read/write; service_role full; platform threat intel readable)
-- ---------------------------------------------------------------------------
ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vulnerabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.threat_intelligence ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.incident_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.playbooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.playbook_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.aggregated_analytics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.export_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.training_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.threat_reports ENABLE ROW LEVEL SECURITY;

-- Assets
DROP POLICY IF EXISTS assets_select_member ON public.assets;
CREATE POLICY assets_select_member ON public.assets
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS assets_service_all ON public.assets;
CREATE POLICY assets_service_all ON public.assets
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Vulnerabilities
DROP POLICY IF EXISTS vulnerabilities_select_member ON public.vulnerabilities;
CREATE POLICY vulnerabilities_select_member ON public.vulnerabilities
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS vulnerabilities_service_all ON public.vulnerabilities;
CREATE POLICY vulnerabilities_service_all ON public.vulnerabilities
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Threat intel: platform rows visible to all authenticated; tenant rows to members
DROP POLICY IF EXISTS threat_intel_select ON public.threat_intelligence;
CREATE POLICY threat_intel_select ON public.threat_intelligence
  FOR SELECT TO authenticated
  USING (
    is_platform = TRUE
    OR (tenant_id IS NOT NULL AND public.is_tenant_member(tenant_id))
  );
DROP POLICY IF EXISTS threat_intel_service_all ON public.threat_intelligence;
CREATE POLICY threat_intel_service_all ON public.threat_intelligence
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Incident cases
DROP POLICY IF EXISTS incident_cases_select_member ON public.incident_cases;
CREATE POLICY incident_cases_select_member ON public.incident_cases
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS incident_cases_service_all ON public.incident_cases;
CREATE POLICY incident_cases_service_all ON public.incident_cases
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Playbooks
DROP POLICY IF EXISTS playbooks_select_member ON public.playbooks;
CREATE POLICY playbooks_select_member ON public.playbooks
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS playbooks_service_all ON public.playbooks;
CREATE POLICY playbooks_service_all ON public.playbooks
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS playbook_actions_select_member ON public.playbook_actions;
CREATE POLICY playbook_actions_select_member ON public.playbook_actions
  FOR SELECT TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.playbooks p
      WHERE p.id = playbook_id AND public.is_tenant_member(p.tenant_id)
    )
  );
DROP POLICY IF EXISTS playbook_actions_service_all ON public.playbook_actions;
CREATE POLICY playbook_actions_service_all ON public.playbook_actions
  FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Analytics / exports / ML
DROP POLICY IF EXISTS aggregated_analytics_select_member ON public.aggregated_analytics;
CREATE POLICY aggregated_analytics_select_member ON public.aggregated_analytics
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS aggregated_analytics_service_all ON public.aggregated_analytics;
CREATE POLICY aggregated_analytics_service_all ON public.aggregated_analytics
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS export_jobs_select_member ON public.export_jobs;
CREATE POLICY export_jobs_select_member ON public.export_jobs
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS export_jobs_service_all ON public.export_jobs;
CREATE POLICY export_jobs_service_all ON public.export_jobs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS training_runs_select_member ON public.training_runs;
CREATE POLICY training_runs_select_member ON public.training_runs
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS training_runs_service_all ON public.training_runs;
CREATE POLICY training_runs_service_all ON public.training_runs
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS threat_reports_select_member ON public.threat_reports;
CREATE POLICY threat_reports_select_member ON public.threat_reports
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS threat_reports_service_all ON public.threat_reports;
CREATE POLICY threat_reports_service_all ON public.threat_reports
  FOR ALL TO service_role USING (true) WITH CHECK (true);
