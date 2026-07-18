-- FORJD post-migration checks (run in Supabase SQL editor).
-- Manual companion to backend/scripts/verify_supabase_post_migration.py

-- Extensions
SELECT extname, extversion
FROM pg_extension
WHERE extname IN ('pgcrypto', 'vector', 'uuid-ossp')
ORDER BY 1;

-- Core tables
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'tenants', 'tenant_members', 'telemetry_events', 'crypto_sessions',
    'stream_results', 'projection_checkpoints', 'projection_dlq',
    'status_pages', 'service_accounts', 'embedding_vectors'
  )
ORDER BY 1;

-- RLS enabled?
SELECT c.relname AS table_name, c.relrowsecurity AS rls_enabled
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind = 'r'
  AND c.relname IN (
    'tenants', 'tenant_members', 'telemetry_events', 'stream_results',
    'crypto_sessions', 'service_accounts', 'embedding_vectors'
  )
ORDER BY 1;

-- Realtime publication
SELECT pubname FROM pg_publication WHERE pubname = 'supabase_realtime';

SELECT n.nspname, c.relname
FROM pg_publication_rel pr
JOIN pg_publication p ON p.oid = pr.prpubid
JOIN pg_class c ON c.oid = pr.prrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE p.pubname = 'supabase_realtime'
ORDER BY 1, 2;

-- Consumer views
SELECT table_name
FROM information_schema.views
WHERE table_schema = 'public'
  AND table_name IN ('projection_feed', 'sealed_events');

-- Optional DEML consolidation schema
SELECT schema_name
FROM information_schema.schemata
WHERE schema_name = 'deml';
