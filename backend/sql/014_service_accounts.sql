-- =============================================================================
-- FORJD service accounts (M2M / subprocessors) — tenant-scoped machine principals
-- =============================================================================
-- Apply after 013_e2ee_hardening.sql.
--
-- Subprocessor model:
--   • Enterprise humans authenticate with Supabase Auth user JWTs + tenant_members.
--   • Trusted partner SaaS backends authenticate with a *tenant-bound* service
--     principal — never a global platform key for tenant data.
--   • Partners keep their own end-user auth; FORJD never sees those end-user tokens.
--   • Service tokens may be opaque (`fjsvc_…`) or Supabase Auth JWTs whose
--     app_metadata.forjd.principal_type = 'service' and match this table.
--   • All writes remain ciphertext-blind; E2EE keys stay client/subprocessor-side.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Tenant-scoped service principals
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.service_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  -- Human-readable label (e.g. "production ingest").
  name TEXT NOT NULL,
  -- Subprocessor slug for audit / policy (e.g. 'partner-app', 'enterprise-direct').
  subprocessor TEXT NOT NULL DEFAULT '',
  -- Opaque token lookup (NULL when JWT-only via auth_user_id).
  prefix TEXT UNIQUE,
  key_hash TEXT,
  -- Optional Supabase Auth user bound for M2M JWTs (app_metadata.forjd).
  auth_user_id UUID UNIQUE,
  -- Capability scopes (see backend AUTH docs). '*' = all scopes.
  scopes TEXT[] NOT NULL DEFAULT ARRAY[
    'ingest:write',
    'ingest:read',
    'projections:read',
    'projections:run'
  ]::text[],
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  revoked_at TIMESTAMPTZ,
  created_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_used_at TIMESTAMPTZ,
  CONSTRAINT service_accounts_auth_or_opaque CHECK (
    auth_user_id IS NOT NULL OR (prefix IS NOT NULL AND key_hash IS NOT NULL)
  ),
  CONSTRAINT service_accounts_name_len CHECK (char_length(name) BETWEEN 1 AND 128),
  CONSTRAINT service_accounts_subprocessor_len CHECK (char_length(subprocessor) <= 64)
);

CREATE INDEX IF NOT EXISTS service_accounts_tenant_idx
  ON public.service_accounts (tenant_id)
  WHERE is_active = TRUE AND revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS service_accounts_prefix_idx
  ON public.service_accounts (prefix)
  WHERE prefix IS NOT NULL AND is_active = TRUE;

ALTER TABLE public.service_accounts ENABLE ROW LEVEL SECURITY;

-- Browser clients: members can list metadata for their tenant (never key_hash).
DROP POLICY IF EXISTS service_accounts_select_member ON public.service_accounts;
CREATE POLICY service_accounts_select_member ON public.service_accounts
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

-- Mutations only via service_role (FastAPI after owner/admin JWT check).
DROP POLICY IF EXISTS service_accounts_service_all ON public.service_accounts;
CREATE POLICY service_accounts_service_all ON public.service_accounts
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT SELECT ON public.service_accounts TO authenticated;
GRANT ALL ON public.service_accounts TO service_role;

-- Hide secrets from PostgREST column grants for authenticated (defense in depth).
REVOKE ALL ON public.service_accounts FROM PUBLIC;
GRANT SELECT (
  id, tenant_id, name, subprocessor, scopes, is_active, revoked_at,
  created_by, created_at, updated_at, last_used_at, auth_user_id, prefix
) ON public.service_accounts TO authenticated;
