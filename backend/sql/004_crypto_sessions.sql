-- =============================================================================
-- FORJD crypto sessions (X25519 public-key directory, server-blind)
-- =============================================================================
-- Apply after 003_secure_tenancy.sql.
--
-- Forward secrecy model (Signal-inspired):
--   • Clients own X25519 identity + ephemeral private keys (never uploaded).
--   • Peers publish only public keys here for session bootstrap / discovery.
--   • Message keys are derived client-side via ECDH + HKDF → AES-256-GCM.
--   • Double Ratchet advances ephemerals per message; compromising one key
--     does not reveal past or future plaintext (forward / future secrecy).
--   • FORJD stores ciphertext + opaque ratchet headers only — zero knowledge
--     of plaintext and of private key material.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Per-tenant / per-device crypto sessions (public material only)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.crypto_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  -- Client-generated session id; typically used as envelope.key_id prefix.
  session_id TEXT NOT NULL,
  -- Supabase user that registered this device session.
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,

  -- X25519 public keys (32 bytes, base64). Private keys NEVER stored.
  identity_public_key TEXT NOT NULL,
  -- Current DH ratchet public key (rotated by the client).
  ephemeral_public_key TEXT,
  -- Opaque client hint (e.g. ratchet counter); server must not interpret.
  ratchet_state_hint TEXT,

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at TIMESTAMPTZ,

  CONSTRAINT crypto_sessions_tenant_session_uidx UNIQUE (tenant_id, session_id),
  CONSTRAINT crypto_sessions_identity_b64 CHECK (char_length(identity_public_key) BETWEEN 40 AND 64)
);

CREATE INDEX IF NOT EXISTS crypto_sessions_tenant_user_idx
  ON public.crypto_sessions (tenant_id, user_id);

CREATE INDEX IF NOT EXISTS crypto_sessions_tenant_updated_idx
  ON public.crypto_sessions (tenant_id, updated_at DESC);

ALTER TABLE public.crypto_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS crypto_sessions_select_member ON public.crypto_sessions;
CREATE POLICY crypto_sessions_select_member ON public.crypto_sessions
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS crypto_sessions_insert_own ON public.crypto_sessions;
CREATE POLICY crypto_sessions_insert_own ON public.crypto_sessions
  FOR INSERT TO authenticated
  WITH CHECK (
    public.is_tenant_member(tenant_id)
    AND user_id = auth.uid()
  );

DROP POLICY IF EXISTS crypto_sessions_update_own ON public.crypto_sessions;
CREATE POLICY crypto_sessions_update_own ON public.crypto_sessions
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid() AND public.is_tenant_member(tenant_id))
  WITH CHECK (user_id = auth.uid() AND public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS crypto_sessions_delete_own ON public.crypto_sessions;
CREATE POLICY crypto_sessions_delete_own ON public.crypto_sessions
  FOR DELETE TO authenticated
  USING (user_id = auth.uid() AND public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS crypto_sessions_service_all ON public.crypto_sessions;
CREATE POLICY crypto_sessions_service_all ON public.crypto_sessions
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.crypto_sessions TO authenticated;
GRANT ALL ON public.crypto_sessions TO service_role;
