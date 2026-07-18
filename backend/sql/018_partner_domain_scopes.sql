-- =============================================================================
-- Partner domain scopes (exports / vulns / integrations / tenant erase)
-- =============================================================================
-- Apply after 017_service_principal_cutover.sql.
--
-- Expands DEFAULT scopes for *new* service_accounts rows. Existing tokens keep
-- their stored scopes — remint via POST /api/v1/service-accounts (or
-- scripts/remint_service_account.sh) after applying this migration.
-- =============================================================================

ALTER TABLE public.service_accounts
  ALTER COLUMN scopes SET DEFAULT ARRAY[
    'ingest:write',
    'ingest:read',
    'projections:read',
    'projections:run',
    'sessions:write',
    'sessions:read',
    'replay:read',
    'replay:write',
    'status:read',
    'status:write',
    'analytics:read',
    'exports:read',
    'exports:write',
    'vulnerabilities:read',
    'vulnerabilities:write',
    'integrations:write',
    'tenants:erase'
  ]::text[];
