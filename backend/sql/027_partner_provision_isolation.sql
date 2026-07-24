-- Partner provision isolation — bind idempotency to partner + external identity.
-- The application serializes first provision/remint with the same composite key.

CREATE UNIQUE INDEX IF NOT EXISTS partner_provisions_partner_external_ref_uidx
  ON public.partner_provisions (partner, external_ref);

COMMENT ON INDEX public.partner_provisions_partner_external_ref_uidx IS
  'Prevents duplicate provisioning per partner identity while isolating partner namespaces.';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.partner_provisions
    GROUP BY tenant_id
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION
      'partner_provisions contains duplicate tenant mappings; repair before migration 027';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM public.partner_provisions
    GROUP BY service_account_id
    HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION
      'partner_provisions contains duplicate service-account mappings; repair before migration 027';
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS partner_provisions_tenant_uidx
  ON public.partner_provisions (tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS partner_provisions_service_account_uidx
  ON public.partner_provisions (service_account_id);
DROP INDEX IF EXISTS public.partner_provisions_tenant_id_idx;

ALTER TABLE public.partner_provisions
  DROP CONSTRAINT IF EXISTS partner_provisions_partner_format;
ALTER TABLE public.partner_provisions
  ADD CONSTRAINT partner_provisions_partner_format CHECK (
    partner = LOWER(BTRIM(partner))
    AND partner ~ '^[a-z0-9][a-z0-9_-]{0,63}$'
  ) NOT VALID;
ALTER TABLE public.partner_provisions
  VALIDATE CONSTRAINT partner_provisions_partner_format;

-- A provision ledger row and its runtime credential must belong to one tenant.
-- Preflight fails closed rather than revoking or exposing a cross-tenant account.
CREATE UNIQUE INDEX IF NOT EXISTS service_accounts_id_tenant_uidx
  ON public.service_accounts (id, tenant_id);

-- IF NOT EXISTS is not sufficient under manual schema drift: a same-name index
-- on different columns would otherwise let this migration drop the old global
-- uniqueness while failing to enforce the replacement contracts.
DO $$
DECLARE
  contract RECORD;
BEGIN
  FOR contract IN
    SELECT *
    FROM (
      VALUES
        (
          'partner_provisions_partner_external_ref_uidx',
          'public.partner_provisions',
          ARRAY['partner', 'external_ref']::TEXT[]
        ),
        (
          'partner_provisions_tenant_uidx',
          'public.partner_provisions',
          ARRAY['tenant_id']::TEXT[]
        ),
        (
          'partner_provisions_service_account_uidx',
          'public.partner_provisions',
          ARRAY['service_account_id']::TEXT[]
        ),
        (
          'service_accounts_id_tenant_uidx',
          'public.service_accounts',
          ARRAY['id', 'tenant_id']::TEXT[]
        )
    ) AS expected(index_name, table_name, columns)
  LOOP
    IF NOT EXISTS (
      SELECT 1
      FROM pg_index AS index_meta
      JOIN pg_class AS index_class
        ON index_class.oid = index_meta.indexrelid
      JOIN pg_namespace AS index_namespace
        ON index_namespace.oid = index_class.relnamespace
      WHERE index_namespace.nspname = 'public'
        AND index_class.relname = contract.index_name
        AND index_meta.indrelid = contract.table_name::REGCLASS
        AND index_meta.indisunique
        AND index_meta.indisvalid
        AND index_meta.indisready
        AND index_meta.indpred IS NULL
        AND index_meta.indexprs IS NULL
        AND index_meta.indnkeyatts = CARDINALITY(contract.columns)
        AND index_meta.indnatts = CARDINALITY(contract.columns)
        AND ARRAY(
          SELECT pg_get_indexdef(index_meta.indexrelid, ordinal, FALSE)
          FROM generate_series(1, index_meta.indnatts) AS ordinal
          ORDER BY ordinal
        ) = contract.columns
    ) THEN
      RAISE EXCEPTION
        'index % has an unexpected definition; repair schema drift before migration 027',
        contract.index_name;
    END IF;
  END LOOP;
END
$$;

ALTER TABLE public.partner_provisions
  DROP CONSTRAINT IF EXISTS partner_provisions_external_ref_key;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM public.partner_provisions AS provision
    LEFT JOIN public.service_accounts AS account
      ON account.id = provision.service_account_id
     AND account.tenant_id = provision.tenant_id
    WHERE account.id IS NULL
  ) THEN
    RAISE EXCEPTION
      'partner_provisions contains a service_account_id/tenant_id mismatch; repair before migration 027';
  END IF;
END
$$;

ALTER TABLE public.partner_provisions
  DROP CONSTRAINT IF EXISTS partner_provisions_service_account_tenant_fkey;
ALTER TABLE public.partner_provisions
  ADD CONSTRAINT partner_provisions_service_account_tenant_fkey
  FOREIGN KEY (service_account_id, tenant_id)
  REFERENCES public.service_accounts (id, tenant_id)
  ON DELETE CASCADE
  NOT VALID;
ALTER TABLE public.partner_provisions
  VALIDATE CONSTRAINT partner_provisions_service_account_tenant_fkey;
ALTER TABLE public.partner_provisions
  DROP CONSTRAINT IF EXISTS partner_provisions_service_account_id_fkey;

-- Active accounts require usable credential material. Revoked accounts may
-- clear key_hash, matching the service-account revoke path.
ALTER TABLE public.service_accounts
  DROP CONSTRAINT IF EXISTS service_accounts_auth_or_opaque;
ALTER TABLE public.service_accounts
  ADD CONSTRAINT service_accounts_auth_or_opaque CHECK (
    NOT is_active
    OR (
      revoked_at IS NULL
      AND (
        auth_user_id IS NOT NULL
        OR (prefix IS NOT NULL AND key_hash IS NOT NULL)
      )
    )
  ) NOT VALID;
ALTER TABLE public.service_accounts
  VALIDATE CONSTRAINT service_accounts_auth_or_opaque;

-- Opaque authentication reads scopes from this row on every request, so active
-- DEML credentials gain the explicit profile permission without token remint.
UPDATE public.service_accounts AS sa
SET scopes = array_append(sa.scopes, 'ml:write'),
    updated_at = NOW()
WHERE sa.is_active
  AND sa.revoked_at IS NULL
  AND NOT ('ml:write' = ANY(sa.scopes))
  AND (
    LOWER(BTRIM(COALESCE(sa.subprocessor, ''))) = 'deml'
    OR EXISTS (
      SELECT 1
      FROM public.partner_provisions AS pp
      WHERE pp.service_account_id = sa.id
        AND LOWER(BTRIM(pp.partner)) = 'deml'
    )
  );
