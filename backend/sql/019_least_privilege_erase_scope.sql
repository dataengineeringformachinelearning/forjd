-- =============================================================================
-- Least privilege: tenants:erase is opt-in (not in DEFAULT scopes)
-- =============================================================================
-- Apply after 018_partner_domain_scopes.sql.
--
-- Existing service_accounts rows keep their stored scopes array. New mints via
-- the API use Python DEFAULT_SCOPES (no erase). Remint with an explicit
-- tenants:erase scope when partner account-deletion sagas need it:
--   scripts/remint_service_account.sh partner-production
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
    'integrations:write'
  ]::text[];
