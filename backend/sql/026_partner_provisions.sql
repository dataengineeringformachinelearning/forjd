-- Partner provision ledger — idempotent DEML (and other subprocessors) tenant minting.
-- Bootstrap auth is FORJD_PROVISION_TOKEN (not tenant fjsvc_). Never stores plaintext tokens.

CREATE TABLE IF NOT EXISTS public.partner_provisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  external_ref TEXT NOT NULL UNIQUE,
  partner TEXT NOT NULL DEFAULT 'deml',
  tenant_id UUID NOT NULL REFERENCES public.tenants (id) ON DELETE CASCADE,
  service_account_id UUID NOT NULL REFERENCES public.service_accounts (id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT partner_provisions_external_ref_format
    CHECK (external_ref ~ '^[a-z0-9][a-z0-9:_-]{3,127}$')
);

CREATE INDEX IF NOT EXISTS partner_provisions_tenant_id_idx
  ON public.partner_provisions (tenant_id);

CREATE INDEX IF NOT EXISTS partner_provisions_partner_idx
  ON public.partner_provisions (partner, created_at DESC);

ALTER TABLE public.partner_provisions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS partner_provisions_service_all ON public.partner_provisions;
CREATE POLICY partner_provisions_service_all ON public.partner_provisions
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);

GRANT ALL ON public.partner_provisions TO service_role;
