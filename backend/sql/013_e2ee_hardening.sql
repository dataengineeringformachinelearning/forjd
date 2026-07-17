-- =============================================================================
-- FORJD E2EE hardening — nonce reuse protection + session revocation
-- =============================================================================
-- Apply after 004 / 010. Server remains ciphertext-blind; these constraints
-- prevent cut-and-paste / nonce reuse and allow device session revoke.
-- =============================================================================

-- --- Nonce uniqueness per tenant session key (AES-GCM nonce must never repeat) ---
CREATE UNIQUE INDEX IF NOT EXISTS telemetry_events_tenant_key_nonce_uidx
  ON public.telemetry_events (tenant_id, key_id, nonce);

-- --- Session revocation (compromised device / logout) ---
ALTER TABLE public.crypto_sessions
  ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS crypto_sessions_tenant_active_idx
  ON public.crypto_sessions (tenant_id, updated_at DESC)
  WHERE revoked_at IS NULL;

COMMENT ON COLUMN public.crypto_sessions.revoked_at IS
  'When set, envelope.key_id matching this session_id is rejected on ingest.';

COMMENT ON INDEX public.telemetry_events_tenant_key_nonce_uidx IS
  'Rejects AES-256-GCM nonce reuse for the same tenant+key_id (forward-secrecy hygiene).';
