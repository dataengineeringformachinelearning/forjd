-- =============================================================================
-- FORJD secure tenancy + E2EE telemetry + vector embeddings (Supabase)
-- =============================================================================
-- Run in the Supabase SQL editor after enabling extensions:
--   Database → Extensions → vector, pgcrypto
--
-- Threat model (Signal-inspired, server-minimal):
--   • Clients own Double Ratchet / key material (forward secrecy on devices).
--   • Server stores AES-256-GCM ciphertext + opaque ratchet headers only.
--   • Server never receives plaintext telemetry payloads on the E2EE path.
--   • RLS scopes every row to tenant membership via auth.uid().
--   • FastAPI uses the service role for ingestion after JWT verification;
--     browser/Realtime clients use the anon key + user JWT (RLS enforced).
--
-- PoC tables (001_pulses, 002_anomaly_embeddings) remain for stack demos;
-- production streaming uses the tables below.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ---------------------------------------------------------------------------
-- Tenants (organizations / workspaces)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  -- Opaque client key-directory handle (e.g. KMS key ARN / device bundle id).
  -- Never store raw AES keys or ratchet secrets here.
  key_directory_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT tenants_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$')
);

CREATE INDEX IF NOT EXISTS tenants_created_at_idx ON public.tenants (created_at DESC);

-- ---------------------------------------------------------------------------
-- Membership: maps Supabase auth.users → tenants (RLS backbone)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.tenant_members (
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member'
    CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (tenant_id, user_id)
);

CREATE INDEX IF NOT EXISTS tenant_members_user_id_idx
  ON public.tenant_members (user_id);

-- ---------------------------------------------------------------------------
-- Helper: is the current JWT user a member of this tenant?
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION public.is_tenant_member(p_tenant_id UUID)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.tenant_members m
    WHERE m.tenant_id = p_tenant_id
      AND m.user_id = auth.uid()
  );
$$;

REVOKE ALL ON FUNCTION public.is_tenant_member(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_tenant_member(UUID) TO authenticated, service_role;

-- ---------------------------------------------------------------------------
-- Encrypted telemetry events (E2EE ingress)
-- Server-visible: tenant, timestamps, crypto metadata, ciphertext bytes.
-- Server-blind: plaintext payload (AES-256-GCM).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.telemetry_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  -- Authenticated Supabase user that submitted the envelope (may be a device user).
  submitted_by UUID REFERENCES auth.users (id) ON DELETE SET NULL,
  -- Client-generated idempotency / stream offset (unique per tenant).
  client_event_id TEXT NOT NULL,
  -- Wall-clock from the client (untrusted); server also has created_at.
  occurred_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Crypto envelope (Signal-style headers are opaque to the server)
  algo TEXT NOT NULL DEFAULT 'aes-256-gcm'
    CHECK (algo IN ('aes-256-gcm')),
  -- Which client key / ratchet chain produced this ciphertext.
  key_id TEXT NOT NULL,
  -- Double Ratchet header blob (base64) — server must not parse.
  ratchet_header TEXT,
  -- 96-bit GCM nonce (12 bytes) as base64.
  nonce TEXT NOT NULL,
  -- Ciphertext + GCM auth tag (base64). Associated data = tenant_id|client_event_id.
  ciphertext TEXT NOT NULL,
  -- Optional SHA-256 of ciphertext for integrity audits without decryption.
  ciphertext_sha256 TEXT,

  -- Minimal non-sensitive routing metadata (never put secrets here).
  content_type TEXT NOT NULL DEFAULT 'application/forjd-telemetry+v1',
  schema_version INT NOT NULL DEFAULT 1,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

  CONSTRAINT telemetry_events_tenant_client_uidx UNIQUE (tenant_id, client_event_id)
);

CREATE INDEX IF NOT EXISTS telemetry_events_tenant_created_idx
  ON public.telemetry_events (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_events_tenant_key_idx
  ON public.telemetry_events (tenant_id, key_id);

-- Realtime: clients can subscribe to inserts for their tenants.
ALTER TABLE public.telemetry_events REPLICA IDENTITY FULL;

-- ---------------------------------------------------------------------------
-- Vector embeddings for anomaly detection (tenant-scoped)
-- Prefer client-sealed scores: store reconstruction_error + encrypted context.
-- Optional clear embedding enables pgvector NN under RLS (reduced confidentiality).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS public.embedding_vectors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  telemetry_event_id UUID REFERENCES public.telemetry_events (id) ON DELETE SET NULL,
  series_id TEXT NOT NULL DEFAULT 'default',
  model_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  -- Dim must match ML_LATENT_DIM (default 16) for the LSTM-AE PoC.
  embedding vector(16),
  reconstruction_error DOUBLE PRECISION,
  is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,

  -- Optional E2EE wrap of the source window / features (server-blind).
  context_ciphertext TEXT,
  context_nonce TEXT,
  context_key_id TEXT,

  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS embedding_vectors_tenant_created_idx
  ON public.embedding_vectors (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS embedding_vectors_tenant_series_idx
  ON public.embedding_vectors (tenant_id, series_id);

CREATE INDEX IF NOT EXISTS embedding_vectors_hnsw_idx
  ON public.embedding_vectors
  USING hnsw (embedding vector_cosine_ops)
  WHERE embedding IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenant_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.telemetry_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.embedding_vectors ENABLE ROW LEVEL SECURITY;

-- Tenants: members can read; only service_role / owners manage writes via API.
DROP POLICY IF EXISTS tenants_select_member ON public.tenants;
CREATE POLICY tenants_select_member ON public.tenants
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(id));

DROP POLICY IF EXISTS tenants_service_all ON public.tenants;
CREATE POLICY tenants_service_all ON public.tenants
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Memberships: users see their own rows; service role full access.
DROP POLICY IF EXISTS tenant_members_select_own ON public.tenant_members;
CREATE POLICY tenant_members_select_own ON public.tenant_members
  FOR SELECT TO authenticated
  USING (user_id = auth.uid() OR public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS tenant_members_service_all ON public.tenant_members;
CREATE POLICY tenant_members_service_all ON public.tenant_members
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Telemetry: members read; members insert for their tenant; no update/delete for users.
DROP POLICY IF EXISTS telemetry_select_member ON public.telemetry_events;
CREATE POLICY telemetry_select_member ON public.telemetry_events
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS telemetry_insert_member ON public.telemetry_events;
CREATE POLICY telemetry_insert_member ON public.telemetry_events
  FOR INSERT TO authenticated
  WITH CHECK (
    public.is_tenant_member(tenant_id)
    AND submitted_by = auth.uid()
  );

DROP POLICY IF EXISTS telemetry_service_all ON public.telemetry_events;
CREATE POLICY telemetry_service_all ON public.telemetry_events
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- Embeddings: same membership boundary.
DROP POLICY IF EXISTS embeddings_select_member ON public.embedding_vectors;
CREATE POLICY embeddings_select_member ON public.embedding_vectors
  FOR SELECT TO authenticated
  USING (public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS embeddings_insert_member ON public.embedding_vectors;
CREATE POLICY embeddings_insert_member ON public.embedding_vectors
  FOR INSERT TO authenticated
  WITH CHECK (public.is_tenant_member(tenant_id));

DROP POLICY IF EXISTS embeddings_service_all ON public.embedding_vectors;
CREATE POLICY embeddings_service_all ON public.embedding_vectors
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

-- ---------------------------------------------------------------------------
-- Grants (Supabase roles)
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;

GRANT SELECT ON public.tenants TO authenticated;
GRANT SELECT ON public.tenant_members TO authenticated;
GRANT SELECT, INSERT ON public.telemetry_events TO authenticated;
GRANT SELECT, INSERT ON public.embedding_vectors TO authenticated;

GRANT ALL ON public.tenants TO service_role;
GRANT ALL ON public.tenant_members TO service_role;
GRANT ALL ON public.telemetry_events TO service_role;
GRANT ALL ON public.embedding_vectors TO service_role;

-- Optional: expose telemetry to Realtime (Dashboard → Replication, or:)
-- ALTER PUBLICATION supabase_realtime ADD TABLE public.telemetry_events;
