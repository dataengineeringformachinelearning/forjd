"""Single source of truth for canonical sealed-ingest request limits."""

from __future__ import annotations

MAX_CIPHERTEXT_BASE64_CHARACTERS = 1_048_576
MAX_INGEST_BATCH_EVENTS = 25
MAX_INGEST_BODY_BYTES = 8 * 1024 * 1024


def ingest_write_paths(api_prefix: str) -> frozenset[str]:
    """Exact FastAPI paths whose JSON bodies carry ingest payloads."""
    prefix = api_prefix.rstrip("/")
    root = f"{prefix}/ingest"
    return frozenset(
        {
            root,
            f"{root}/events",
            f"{root}/events:batch",
            f"{root}/embeddings",
        }
    )
