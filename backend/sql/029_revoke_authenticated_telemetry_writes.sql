-- 029: Close direct Supabase client write bypass for sealed telemetry paths.
-- FastAPI (service_role / server pool) remains the only writer for ingest tables.
-- Authenticated members retain SELECT via RLS; INSERT policies/grants are revoked.

BEGIN;

DROP POLICY IF EXISTS telemetry_insert_member ON public.telemetry_events;
DROP POLICY IF EXISTS embeddings_insert_member ON public.embedding_vectors;

REVOKE INSERT ON public.telemetry_events FROM authenticated;
REVOKE INSERT ON public.embedding_vectors FROM authenticated;

COMMIT;
