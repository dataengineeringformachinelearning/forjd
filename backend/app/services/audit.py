"""Append-only audit log — security-relevant actions, never plaintext payloads.

Records metadata only (actor, action, tenant, resource ids). Ciphertext and
message keys must never appear in `details`.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg

logger = logging.getLogger("forjd.audit")

# --- Allowed action vocabulary (keep small + stable for SIEM filters) ---
ACTION_INGEST_BATCH = "ingest.batch"
ACTION_SESSION_UPSERT = "session.upsert"
ACTION_TENANT_CREATE = "tenant.create"
ACTION_PROJECTION_RUN = "projection.run"
ACTION_REPLAY = "replay.run"
ACTION_DLQ_RETRY = "replay.dlq_retry"


# --- Ensure table exists (soft path for local; production applies sql/010) ---
async def ensure_audit_schema(pool: asyncpg.Pool) -> None:
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            actor_user_id TEXT,
            tenant_id UUID,
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL DEFAULT '',
            resource_id TEXT NOT NULL DEFAULT '',
            details JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )


# --- Write one audit row (best-effort; never fail the primary request) ---
async def record(
    pool: asyncpg.Pool,
    *,
    action: str,
    actor_user_id: str | None = None,
    tenant_id: UUID | str | None = None,
    resource_type: str = "",
    resource_id: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    """Persist an audit event. Swallows DB errors so audit never breaks ingest."""
    safe = _sanitize_details(details or {})
    try:
        await pool.execute(
            """
            INSERT INTO audit_events (
                actor_user_id, tenant_id, action,
                resource_type, resource_id, details
            )
            VALUES ($1, $2::uuid, $3, $4, $5, $6::jsonb)
            """,
            actor_user_id,
            str(tenant_id) if tenant_id else None,
            action[:128],
            (resource_type or "")[:64],
            (resource_id or "")[:256],
            json.dumps(safe),
        )
    except Exception as exc:  # noqa: BLE001
        # Table may be missing before sql/010 — try soft-create once, then retry.
        logger.debug("audit write failed (will soft-create): %s", exc)
        try:
            await ensure_audit_schema(pool)
            await pool.execute(
                """
                INSERT INTO audit_events (
                    actor_user_id, tenant_id, action,
                    resource_type, resource_id, details
                )
                VALUES ($1, $2::uuid, $3, $4, $5, $6::jsonb)
                """,
                actor_user_id,
                str(tenant_id) if tenant_id else None,
                action[:128],
                (resource_type or "")[:64],
                (resource_id or "")[:256],
                json.dumps(safe),
            )
        except Exception as retry_exc:  # noqa: BLE001
            logger.warning("audit write dropped: %s", retry_exc)


# --- Strip anything that looks like ciphertext / keys ---
_FORBIDDEN_KEYS = frozenset(
    {
        "ciphertext",
        "plaintext",
        "nonce",
        "key",
        "private_key",
        "secret",
        "password",
        "token",
        "ratchet_header",
        "message_key",
        "session_key",
    }
)


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in details.items():
        lk = str(key).lower()
        if lk in _FORBIDDEN_KEYS or any(p in lk for p in ("cipher", "secret", "private")):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list) and all(
            isinstance(x, (str, int, float, bool)) for x in value[:50]
        ):
            out[key] = value[:50]
        elif isinstance(value, dict):
            out[key] = _sanitize_details(value)
    return out
