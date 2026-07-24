-- =============================================================================
-- FORJD status child tenant integrity
-- =============================================================================
-- Bind every service/incident to the tenant of its parent page at the database
-- boundary. Preflight fails closed instead of legitimizing historical mismatch.

-- Engine readiness resolves the newest observation independently per service.
CREATE INDEX IF NOT EXISTS health_probe_observations_service_observed_idx
  ON public.health_probe_observations (service_id, observed_at DESC)
  INCLUDE (is_active);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_index AS index_meta
    JOIN pg_class AS index_class
      ON index_class.oid = index_meta.indexrelid
    JOIN pg_namespace AS index_namespace
      ON index_namespace.oid = index_class.relnamespace
    WHERE index_namespace.nspname = 'public'
      AND index_class.relname = 'health_probe_observations_service_observed_idx'
      AND index_meta.indrelid = 'public.health_probe_observations'::REGCLASS
      AND NOT index_meta.indisunique
      AND index_meta.indisvalid
      AND index_meta.indisready
      AND index_meta.indpred IS NULL
      AND index_meta.indexprs IS NULL
      AND index_meta.indnkeyatts = 2
      AND index_meta.indnatts = 3
      AND ARRAY(
        SELECT pg_get_indexdef(index_meta.indexrelid, ordinal, FALSE)
        FROM generate_series(1, index_meta.indnatts) AS ordinal
        ORDER BY ordinal
      ) = ARRAY['service_id', 'observed_at DESC', 'is_active']::TEXT[]
  ) THEN
    RAISE EXCEPTION
      'health_probe_observations_service_observed_idx has an unexpected definition; repair schema drift before migration 028';
  END IF;
END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.status_services AS child
    LEFT JOIN public.status_pages AS parent
      ON parent.id = child.page_id
     AND parent.tenant_id = child.tenant_id
    WHERE parent.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'status_services contains a page_id/tenant_id mismatch; repair before migration 028';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.status_incidents AS child
    LEFT JOIN public.status_pages AS parent
      ON parent.id = child.page_id
     AND parent.tenant_id = child.tenant_id
    WHERE parent.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'status_incidents contains a page_id/tenant_id mismatch; repair before migration 028';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.health_probe_observations AS child
    LEFT JOIN public.status_services AS parent
      ON parent.id = child.service_id
     AND parent.tenant_id = child.tenant_id
    WHERE parent.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'health_probe_observations contains a service_id/tenant_id mismatch; repair before migration 028';
  END IF;
END
$$;

-- Recreate exact definitions so a same-name manual constraint cannot weaken
-- the contract. Dropping and rebuilding is safe inside the migration transaction.
ALTER TABLE public.health_probe_observations
  DROP CONSTRAINT IF EXISTS health_probe_observations_service_tenant_fkey;
ALTER TABLE public.status_services
  DROP CONSTRAINT IF EXISTS status_services_page_tenant_fkey;
ALTER TABLE public.status_incidents
  DROP CONSTRAINT IF EXISTS status_incidents_page_tenant_fkey;
ALTER TABLE public.status_services
  DROP CONSTRAINT IF EXISTS status_services_id_tenant_key;
ALTER TABLE public.status_pages
  DROP CONSTRAINT IF EXISTS status_pages_id_tenant_key;
ALTER TABLE public.status_pages
  ADD CONSTRAINT status_pages_id_tenant_key UNIQUE (id, tenant_id);

ALTER TABLE public.status_services
  ADD CONSTRAINT status_services_page_tenant_fkey
  FOREIGN KEY (page_id, tenant_id)
  REFERENCES public.status_pages (id, tenant_id)
  ON DELETE CASCADE
  NOT VALID;
ALTER TABLE public.status_incidents
  ADD CONSTRAINT status_incidents_page_tenant_fkey
  FOREIGN KEY (page_id, tenant_id)
  REFERENCES public.status_pages (id, tenant_id)
  ON DELETE CASCADE
  NOT VALID;

ALTER TABLE public.status_services
  ADD CONSTRAINT status_services_id_tenant_key UNIQUE (id, tenant_id);
ALTER TABLE public.health_probe_observations
  ADD CONSTRAINT health_probe_observations_service_tenant_fkey
  FOREIGN KEY (service_id, tenant_id)
  REFERENCES public.status_services (id, tenant_id)
  ON DELETE CASCADE
  NOT VALID;

ALTER TABLE public.status_services
  VALIDATE CONSTRAINT status_services_page_tenant_fkey;
ALTER TABLE public.status_incidents
  VALIDATE CONSTRAINT status_incidents_page_tenant_fkey;
ALTER TABLE public.health_probe_observations
  VALIDATE CONSTRAINT health_probe_observations_service_tenant_fkey;

ALTER TABLE public.status_services
  DROP CONSTRAINT IF EXISTS status_services_page_id_fkey;
ALTER TABLE public.status_incidents
  DROP CONSTRAINT IF EXISTS status_incidents_page_id_fkey;
ALTER TABLE public.health_probe_observations
  DROP CONSTRAINT IF EXISTS health_probe_observations_service_id_fkey;
