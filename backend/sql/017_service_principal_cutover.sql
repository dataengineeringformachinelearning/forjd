-- =============================================================================
-- FORJD service-principal cutover (sessions actor id + expanded default scopes)
-- =============================================================================
-- Apply after 016_ml_supabase.sql.
--
-- Goals:
--   • crypto_sessions.user_id is an opaque actor UUID (human Auth sub OR
--     service_accounts.id). Drop the auth.users FK so subprocessors can
--     register X25519 public keys with fjsvc_ tokens when
--     REQUIRE_CRYPTO_SESSION=true.
--   • Expand default service-account scopes for partner control-plane adapters:
--     sessions, replay/DLQ, status management, analytics:read.
--
-- Isolation unchanged: service tokens remain hard-bound to one tenant_id;
-- FastAPI enforces scopes via require_tenant_access.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- crypto_sessions.user_id — opaque actor (human or service), no auth.users FK
-- ---------------------------------------------------------------------------
DO $$
DECLARE
  fk_name text;
BEGIN
  SELECT c.conname INTO fk_name
  FROM pg_constraint c
  JOIN pg_class t ON t.oid = c.conrelid
  JOIN pg_namespace n ON n.oid = t.relnamespace
  WHERE n.nspname = 'public'
    AND t.relname = 'crypto_sessions'
    AND c.contype = 'f'
    AND pg_get_constraintdef(c.oid) ILIKE '%user_id%auth.users%';

  IF fk_name IS NOT NULL THEN
    EXECUTE format('ALTER TABLE public.crypto_sessions DROP CONSTRAINT %I', fk_name);
  END IF;
END $$;

COMMENT ON COLUMN public.crypto_sessions.user_id IS
  'Opaque actor UUID: Supabase auth.users.id for humans, or service_accounts.id for fjsvc_ subprocessors. Not FK-bound so machine principals can register sessions.';

-- ---------------------------------------------------------------------------
-- Service-account default scopes (new rows; existing rows unchanged)
-- ---------------------------------------------------------------------------
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
    'analytics:read'
  ]::text[];
