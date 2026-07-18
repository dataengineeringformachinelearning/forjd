-- =============================================================================
-- FORJD domain scanners / reports (wave 2)
-- =============================================================================
-- Apply after 011. Lighthouse, OSINT endpoints, validated sites, honeypots, reports.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.lighthouse_scans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  performance DOUBLE PRECISION NOT NULL DEFAULT 0,
  accessibility DOUBLE PRECISION NOT NULL DEFAULT 0,
  best_practices DOUBLE PRECISION NOT NULL DEFAULT 0,
  seo DOUBLE PRECISION NOT NULL DEFAULT 0,
  raw_payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS lighthouse_scans_tenant_idx
  ON public.lighthouse_scans (tenant_id, scanned_at DESC);

CREATE TABLE IF NOT EXISTS public.discovered_endpoints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'crt.sh',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, url)
);

CREATE TABLE IF NOT EXISTS public.validated_sites (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  domain TEXT NOT NULL,
  is_verified BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, domain)
);

CREATE TABLE IF NOT EXISTS public.web_technology_observations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  validated_site_id UUID NOT NULL REFERENCES public.validated_sites (id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT 'firecrawl',
  source_url TEXT NOT NULL,
  technology_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  version TEXT NOT NULL DEFAULT '',
  confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
  evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  cpe_2_3 TEXT NOT NULL DEFAULT '',
  cve_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (validated_site_id, source, normalized_name, version)
);

CREATE TABLE IF NOT EXISTS public.honeypot_endpoints (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  trap_type TEXT NOT NULL DEFAULT 'generic',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, path)
);

CREATE TABLE IF NOT EXISTS public.honeypot_interactions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  honeypot_id UUID NOT NULL REFERENCES public.honeypot_endpoints (id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  source_ip INET,
  method TEXT NOT NULL DEFAULT 'GET',
  user_agent TEXT,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS honeypot_interactions_tenant_idx
  ON public.honeypot_interactions (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.report_archives (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  object_key TEXT,
  checksum_sha256 TEXT,
  row_count INT NOT NULL DEFAULT 0,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_by_actor_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS report_archives_tenant_idx
  ON public.report_archives (tenant_id, created_at DESC);

-- RLS
ALTER TABLE public.lighthouse_scans ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.discovered_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.validated_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.web_technology_observations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.honeypot_endpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.honeypot_interactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.report_archives ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'lighthouse_scans',
    'discovered_endpoints',
    'validated_sites',
    'web_technology_observations',
    'honeypot_endpoints',
    'honeypot_interactions',
    'report_archives'
  ]
  LOOP
    EXECUTE format(
      'DROP POLICY IF EXISTS %I_select_member ON public.%I;
       CREATE POLICY %I_select_member ON public.%I
         FOR SELECT TO authenticated
         USING (public.is_tenant_member(tenant_id));
       DROP POLICY IF EXISTS %I_service_all ON public.%I;
       CREATE POLICY %I_service_all ON public.%I
         FOR ALL TO service_role USING (true) WITH CHECK (true);',
      t, t, t, t, t, t, t, t
    );
  END LOOP;
END $$;
