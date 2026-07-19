-- Historical global embeddings table (unused by the API; prefer tenant-scoped /api/v1/ml).
-- Enable the vector extension before applying on fresh databases.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS anomaly_embeddings (
  id UUID PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  series_id TEXT NOT NULL DEFAULT 'default',
  model_version TEXT NOT NULL,
  -- Named series_window (not "window") — WINDOW is reserved in PostgreSQL.
  series_window JSONB NOT NULL DEFAULT '[]'::jsonb,
  -- Must match Settings.ML_LATENT_DIM (default 16).
  embedding vector(16) NOT NULL,
  reconstruction_error DOUBLE PRECISION NOT NULL,
  is_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS anomaly_embeddings_created_at_idx
  ON anomaly_embeddings (created_at DESC);

CREATE INDEX IF NOT EXISTS anomaly_embeddings_series_id_idx
  ON anomaly_embeddings (series_id);

-- HNSW for cosine nearest-neighbor lookup (works well at PoC scale).
CREATE INDEX IF NOT EXISTS anomaly_embeddings_embedding_hnsw_idx
  ON anomaly_embeddings
  USING hnsw (embedding vector_cosine_ops);
