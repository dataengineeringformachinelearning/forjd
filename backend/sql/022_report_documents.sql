-- =============================================================================
-- Tenant-scoped report documents (partner user reports / issue documents)
-- =============================================================================
-- Apply after 021_ingest_projection_reliability.sql.
--
-- Durable document storage for partner-submitted reports (e.g. DEML issue
-- reports). Bodies are bounded, pre-redacted text from the partner BFF;
-- context is a strict PII-minimized metadata map. Never ciphertext or keys.
-- Adds reports:read / reports:write to DEFAULT scopes for *new*
-- service_accounts rows — remint existing tokens to pick the scopes up.
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.report_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  client_report_id UUID NOT NULL,
  content_sha256 TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'issue_report',
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  context JSONB NOT NULL DEFAULT '{}'::jsonb,
  submitted_by_pseudonym TEXT,
  created_by_actor_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT report_documents_kind_shape CHECK (kind ~ '^[a-z][a-z0-9_.-]{0,63}$'),
  CONSTRAINT report_documents_title_len CHECK (char_length(title) BETWEEN 1 AND 255),
  CONSTRAINT report_documents_body_len CHECK (char_length(body) <= 8000),
  CONSTRAINT report_documents_context_object CHECK (jsonb_typeof(context) = 'object'),
  CONSTRAINT report_documents_content_sha256_shape CHECK (
    content_sha256 ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT report_documents_pseudonym_len CHECK (
    submitted_by_pseudonym IS NULL OR char_length(submitted_by_pseudonym) BETWEEN 1 AND 128
  ),
  -- Reports are metadata + redacted text; sealed evidence stays on the ingest lane.
  CONSTRAINT report_documents_no_raw_fields CHECK (
    NOT (context ?| ARRAY[
      'raw', 'raw_payload', 'ciphertext', 'plaintext', 'password', 'secret',
      'token', 'authorization', 'cookie', 'email', 'username'
    ])
  )
);

CREATE INDEX IF NOT EXISTS report_documents_tenant_created_idx
  ON public.report_documents (tenant_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS report_documents_tenant_kind_idx
  ON public.report_documents (tenant_id, kind, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS report_documents_tenant_client_idx
  ON public.report_documents (tenant_id, client_report_id);

-- --- RLS: members read their tenant; writes go through the service plane ---
ALTER TABLE public.report_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS report_documents_select_member ON public.report_documents;
CREATE POLICY report_documents_select_member ON public.report_documents
  FOR SELECT TO authenticated USING (public.is_tenant_member(tenant_id));
DROP POLICY IF EXISTS report_documents_service_all ON public.report_documents;
CREATE POLICY report_documents_service_all ON public.report_documents
  FOR ALL TO service_role USING (true) WITH CHECK (true);

GRANT SELECT ON public.report_documents TO authenticated;
GRANT ALL ON public.report_documents TO service_role;

-- --- Default scopes for new service accounts (existing tokens: remint) ---
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
    'ml:read',
    'exports:read',
    'exports:write',
    'vulnerabilities:read',
    'vulnerabilities:write',
    'integrations:write',
    'siem:read',
    'siem:write',
    'cases:read',
    'cases:write',
    'playbooks:read',
    'playbooks:write',
    'playbooks:execute',
    'threat-intel:read',
    'reports:read',
    'reports:write'
  ]::text[];

COMMENT ON TABLE public.report_documents IS
  'Tenant-scoped partner report documents (bounded, pre-redacted text + PII-minimized context).';
