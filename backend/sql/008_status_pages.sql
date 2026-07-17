-- =============================================================================
-- FORJD status pages (operational visibility for any SaaS tenant)
-- =============================================================================
-- Apply after 003. Public read when is_published; members manage via JWT API.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.status_pages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  is_published BOOLEAN NOT NULL DEFAULT FALSE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT status_pages_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$')
);

CREATE INDEX IF NOT EXISTS status_pages_tenant_idx
  ON public.status_pages (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.status_services (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  page_id UUID NOT NULL REFERENCES public.status_pages (id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  -- operational | degraded | partial_outage | major_outage | maintenance
  status TEXT NOT NULL DEFAULT 'operational'
    CHECK (status IN (
      'operational', 'degraded', 'partial_outage', 'major_outage', 'maintenance'
    )),
  description TEXT NOT NULL DEFAULT '',
  sort_order INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS status_services_page_idx
  ON public.status_services (page_id, sort_order);

CREATE TABLE IF NOT EXISTS public.status_incidents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  page_id UUID NOT NULL REFERENCES public.status_pages (id) ON DELETE CASCADE,
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'investigating'
    CHECK (status IN (
      'investigating', 'identified', 'monitoring', 'resolved'
    )),
  severity TEXT NOT NULL DEFAULT 'minor'
    CHECK (severity IN ('minor', 'major', 'critical')),
  body TEXT NOT NULL DEFAULT '',
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS status_incidents_page_idx
  ON public.status_incidents (page_id, started_at DESC);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE public.status_pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.status_services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.status_incidents ENABLE ROW LEVEL SECURITY;

-- Members manage; anyone can SELECT published pages (anon + authenticated).
DROP POLICY IF EXISTS status_pages_select_public ON public.status_pages;
CREATE POLICY status_pages_select_public ON public.status_pages
  FOR SELECT TO anon, authenticated
  USING (is_published = TRUE OR public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS status_pages_service_all ON public.status_pages;
CREATE POLICY status_pages_service_all ON public.status_pages
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS status_services_select_public ON public.status_services;
CREATE POLICY status_services_select_public ON public.status_services
  FOR SELECT TO anon, authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.status_pages p
      WHERE p.id = page_id
        AND (p.is_published = TRUE OR public.is_tenant_member(p.tenant_id))
    )
  );

DROP POLICY IF EXISTS status_services_service_all ON public.status_services;
CREATE POLICY status_services_service_all ON public.status_services
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS status_incidents_select_public ON public.status_incidents;
CREATE POLICY status_incidents_select_public ON public.status_incidents
  FOR SELECT TO anon, authenticated
  USING (
    EXISTS (
      SELECT 1 FROM public.status_pages p
      WHERE p.id = page_id
        AND (p.is_published = TRUE OR public.is_tenant_member(p.tenant_id))
    )
  );

DROP POLICY IF EXISTS status_incidents_service_all ON public.status_incidents;
CREATE POLICY status_incidents_service_all ON public.status_incidents
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT ON public.status_pages, public.status_services, public.status_incidents
  TO anon, authenticated;
GRANT ALL ON public.status_pages, public.status_services, public.status_incidents
  TO service_role;
