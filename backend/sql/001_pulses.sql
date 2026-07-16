-- FORJD pulse PoC table (run in Supabase SQL editor or psql)
-- Soft-create also happens on first POST /api/v1/pulse when the API can write.

CREATE TABLE IF NOT EXISTS pulses (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source TEXT NOT NULL DEFAULT 'api',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  result JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS pulses_created_at_idx ON pulses (created_at DESC);
