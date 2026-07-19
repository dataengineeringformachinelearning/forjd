-- Historical legacy table (unused by the API; kept for existing databases).

CREATE TABLE IF NOT EXISTS pulses (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  source TEXT NOT NULL DEFAULT 'api',
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  result JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS pulses_created_at_idx ON pulses (created_at DESC);
