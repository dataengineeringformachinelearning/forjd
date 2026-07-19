"""Idempotent durable tenant erase for partner account deletion."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.tenant_erase")

# --- Tenant-scoped tables (best-effort; missing tables are skipped) ---
_ERASE_TABLES: tuple[str, ...] = (
    "ml_scores",
    "embedding_vectors",
    "training_runs",
    "export_jobs",
    "vulnerabilities",
    "assets",
    "threat_intelligence",
    "incident_cases",
    "playbook_actions",
    "playbooks",
    "status_incidents",
    "status_services",
    "status_pages",
    "projection_dlq",
    "projection_checkpoints",
    "stream_results",
    "telemetry_events",  # sealed_events is a view over this table
    "crypto_sessions",
    "audit_events",
    "discovered_endpoints",
    "validated_sites",
    "lighthouse_scans",
    "honeypot_events",
    "report_archives",
    "outbox_events",
)


async def erase_tenant(
    pool: asyncpg.Pool,
    *,
    principal: AuthUser,
    tenant_id: UUID,
) -> dict[str, Any]:
    """Delete durable tenant data and revoke service credentials.

    Authorization: human owner/admin **or** service principal with ``tenants:erase``
    bound to this tenant. Idempotent — a missing tenant still returns ok.
    """
    await tenant_svc.require_tenant_access(
        pool,
        principal=principal,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"tenants:erase"}),
    )

    deleted: dict[str, int] = {}
    async with pool.acquire() as conn, conn.transaction():
        for table in _ERASE_TABLES:
            try:
                status = await conn.execute(
                    f"DELETE FROM public.{table} WHERE tenant_id = $1::uuid",
                    str(tenant_id),
                )
                # asyncpg returns e.g. "DELETE 3"
                count = int(str(status).rsplit(" ", 1)[-1])
                if count:
                    deleted[table] = count
            except asyncpg.UndefinedTableError:
                continue
            except asyncpg.PostgresError as exc:
                logger.warning("erase skip %s: %s", table, exc)
                continue

        # Drop credentials + memberships + tenant (CASCADE covers leftovers).
        sa = await conn.execute(
            "DELETE FROM public.service_accounts WHERE tenant_id = $1::uuid",
            str(tenant_id),
        )
        deleted["service_accounts"] = int(str(sa).rsplit(" ", 1)[-1])
        await conn.execute(
            "DELETE FROM public.tenant_members WHERE tenant_id = $1::uuid",
            str(tenant_id),
        )
        tenant_del = await conn.execute(
            "DELETE FROM public.tenants WHERE id = $1::uuid",
            str(tenant_id),
        )
        deleted["tenants"] = int(str(tenant_del).rsplit(" ", 1)[-1])

    logger.info("tenant erase complete tenant_id=%s deleted=%s", tenant_id, deleted)
    return {"ok": True, "tenant_id": str(tenant_id), "deleted": deleted}
