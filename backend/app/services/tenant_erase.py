"""Idempotent durable tenant erase for partner account deletion."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from uuid import UUID

import asyncpg

from app.core import object_storage
from app.core.auth import AuthUser
from app.core.config import settings
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.tenant_erase")

# Known tables with a direct tenant_id column, ordered children before parents.
# Existence/column shape is discovered before DELETE; SQL errors are never
# swallowed inside the erase transaction.
_ERASE_TABLES: tuple[str, ...] = (
    "playbook_runs",  # cascades playbook_action_results
    "security_signals",
    "correlation_receipts",  # incident_cases.source_correlation_id ON DELETE SET NULL
    "ml_scores",
    "embedding_vectors",
    "training_runs",
    "threat_reports",
    "export_jobs",
    "vulnerabilities",
    "assets",
    "threat_intelligence",
    "incident_cases",
    "playbooks",
    "status_incidents",
    "status_services",
    "status_pages",
    "projection_dlq",
    "projection_checkpoints",
    "stream_results",
    "telemetry_events",  # sealed_events is a view over this table
    "crypto_sessions",
    # audit_events is append-only compliance evidence and deliberately survives
    # tenant erasure after sql/020 drops its mutable tenant FK.
    "aggregated_analytics",
    "telemetry_ingest_receipts",
    "endpoint_observations",
    "health_probe_observations",
    "daemon_api_keys",
    "discovered_endpoints",
    "validated_sites",
    "lighthouse_scans",
    "web_technology_observations",
    "honeypot_endpoints",
    "honeypot_interactions",
    "report_archives",
    "report_documents",
    "service_accounts",
)


def _delete_count(status: str) -> int:
    return int(str(status).rsplit(" ", 1)[-1])


def _receipt_result(row: Any) -> dict[str, Any]:
    counts = row["deleted_counts"] or {}
    if isinstance(counts, str):
        counts = json.loads(counts)
    return {
        "ok": True,
        "tenant_id": str(row["tenant_id"]),
        "deleted": counts,
        "idempotent_replay": True,
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }


def _principal_can_read_receipt(principal: AuthUser, row: Any, tenant_id: UUID) -> bool:
    if row["requested_by"] == principal.actor_id:
        return True
    if principal.is_erase_tombstone:
        return principal.tenant_id == str(tenant_id)
    return (
        principal.is_service
        and principal.tenant_id == str(tenant_id)
        and ("tenants:erase" in principal.scopes or "*" in principal.scopes)
    )


def _credential_tombstone(principal: AuthUser) -> tuple[str | None, str | None]:
    """Return verified opaque-token metadata suitable for a durable receipt."""
    prefix = principal.opaque_token_prefix
    token_hash = principal.opaque_token_hash
    if prefix is None and token_hash is None:
        return None, None
    if (
        not principal.is_service
        or prefix is None
        or token_hash is None
        or len(prefix) != 8
        or len(token_hash) != 64
        or any(char not in "0123456789abcdef" for char in token_hash)
    ):
        raise RuntimeError("invalid authenticated opaque credential metadata")
    return prefix, token_hash


async def _delete_artifacts(keys: list[str]) -> int:
    """Delete tenant artifacts before their durable rows are erased."""
    storage_keys: list[str] = []
    local_roots = {
        (Path(settings.ML_MODEL_DIR).parent / "exports").resolve(),
        (Path(settings.ML_MODEL_DIR).parent / "reports").resolve(),
    }
    deleted = 0
    for raw_key in dict.fromkeys(keys):
        if not raw_key:
            continue
        path = Path(raw_key.removeprefix("local:")).resolve()
        is_local = (
            raw_key.startswith("local:")
            or raw_key.startswith("/")
            or any(path.is_relative_to(root) for root in local_roots)
        )
        if not is_local:
            storage_keys.append(raw_key)
            continue
        if not any(path.is_relative_to(root) for root in local_roots):
            raise RuntimeError("refusing to erase an artifact outside FORJD storage roots")
        existed = path.exists()
        await asyncio.to_thread(path.unlink, missing_ok=True)
        deleted += int(existed)
    if storage_keys:
        if not object_storage.is_configured():
            raise RuntimeError("tenant artifacts exist but object storage is unavailable")
        await asyncio.to_thread(object_storage.delete_objects, keys=storage_keys)
        deleted += len(storage_keys)
    return deleted


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
    prior = await pool.fetchrow(
        """
        SELECT tenant_id::text, requested_by, status, deleted_counts, completed_at
        FROM tenant_erase_receipts
        WHERE tenant_id = $1::uuid AND status = 'completed'
        """,
        str(tenant_id),
    )
    if prior is not None and _principal_can_read_receipt(principal, prior, tenant_id):
        return _receipt_result(prior)

    await tenant_svc.require_tenant_access(
        pool,
        principal=principal,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin"}),
        required_scopes=frozenset({"tenants:erase"}),
    )
    credential_prefix, credential_hash = _credential_tombstone(principal)

    deleted: dict[str, int] = {}
    async with pool.acquire() as conn, conn.transaction():
        await conn.fetchval(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"forjd:tenant-erase:{tenant_id}",
        )

        prior = await conn.fetchrow(
            """
            SELECT tenant_id::text, requested_by, status, deleted_counts, completed_at
            FROM tenant_erase_receipts
            WHERE tenant_id = $1::uuid AND status = 'completed'
            """,
            str(tenant_id),
        )
        if prior is not None:
            return _receipt_result(prior)

        await conn.execute(
            """
            INSERT INTO tenant_erase_receipts (
                tenant_id, requested_by, status, deleted_counts,
                erased_credential_prefix, erased_credential_hash, updated_at
            )
            VALUES ($1::uuid, $2, 'pending', '{}'::jsonb, $3, $4, NOW())
            ON CONFLICT (tenant_id) DO UPDATE SET
                requested_by = EXCLUDED.requested_by,
                erased_credential_prefix = COALESCE(
                    EXCLUDED.erased_credential_prefix,
                    tenant_erase_receipts.erased_credential_prefix
                ),
                erased_credential_hash = COALESCE(
                    EXCLUDED.erased_credential_hash,
                    tenant_erase_receipts.erased_credential_hash
                ),
                updated_at = NOW()
            WHERE tenant_erase_receipts.status <> 'completed'
            """,
            str(tenant_id),
            principal.actor_id,
            credential_prefix,
            credential_hash,
        )

        # The array supports the stored contract, but current acceptance emits
        # one tenant per receipt. Deleting the matching receipt therefore
        # cannot discard another tenant's accepted processing work.
        processing_exists = await conn.fetchval(
            "SELECT to_regclass('public.ingest_processing_batches') IS NOT NULL"
        )
        if processing_exists:
            processing = await conn.execute(
                """
                DELETE FROM public.ingest_processing_batches
                WHERE $1::uuid = ANY(tenant_ids)
                """,
                str(tenant_id),
            )
            processing_count = _delete_count(processing)
            if processing_count:
                deleted["ingest_processing_batches"] = processing_count

        present_rows = await conn.fetch(
            """
            SELECT DISTINCT table_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND column_name = 'tenant_id'
              AND table_name = ANY($1::text[])
            """,
            list(_ERASE_TABLES),
        )
        present = {str(row["table_name"]) for row in present_rows}

        artifact_queries: list[str] = []
        if "export_jobs" in present:
            artifact_queries.append(
                "SELECT object_key FROM public.export_jobs "
                "WHERE tenant_id = $1::uuid AND object_key IS NOT NULL"
            )
        if "report_archives" in present:
            artifact_queries.append(
                "SELECT object_key FROM public.report_archives "
                "WHERE tenant_id = $1::uuid AND object_key IS NOT NULL"
            )
        if artifact_queries:
            artifact_rows = await conn.fetch(
                " UNION ALL ".join(artifact_queries),
                str(tenant_id),
            )
            artifact_count = await _delete_artifacts(
                [str(row["object_key"]) for row in artifact_rows]
            )
            if artifact_count:
                deleted["stored_artifacts"] = artifact_count

        for table in _ERASE_TABLES:
            if table not in present:
                continue
            status = await conn.execute(
                f"DELETE FROM public.{table} WHERE tenant_id = $1::uuid",
                str(tenant_id),
            )
            count = _delete_count(status)
            if count:
                deleted[table] = count

        # Outbox has no tenant column; remove tenant-tagged unpublished/history
        # payloads explicitly before deleting the tenant.
        outbox_exists = await conn.fetchval(
            "SELECT to_regclass('public.outbox_events') IS NOT NULL"
        )
        if outbox_exists:
            outbox = await conn.execute(
                """
                DELETE FROM public.outbox_events
                WHERE payload ->> 'tenant_id' = $1
                   OR payload ->> 'account_id' = $1
                   OR headers ->> 'tenant_id' = $1
                   OR key = $1
                """,
                str(tenant_id),
            )
            outbox_count = _delete_count(outbox)
            if outbox_count:
                deleted["outbox_events"] = outbox_count

        members = await conn.execute(
            "DELETE FROM public.tenant_members WHERE tenant_id = $1::uuid",
            str(tenant_id),
        )
        member_count = _delete_count(members)
        if member_count:
            deleted["tenant_members"] = member_count
        tenant_del = await conn.execute(
            "DELETE FROM public.tenants WHERE id = $1::uuid",
            str(tenant_id),
        )
        deleted["tenants"] = _delete_count(tenant_del)

        receipt = await conn.fetchrow(
            """
            UPDATE tenant_erase_receipts
            SET status = 'completed',
                deleted_counts = $2::jsonb,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE tenant_id = $1::uuid
            RETURNING tenant_id::text, requested_by, status,
                      deleted_counts, completed_at
            """,
            str(tenant_id),
            json.dumps(deleted, sort_keys=True),
        )

    logger.info("tenant erase complete tenant_id=%s deleted=%s", tenant_id, deleted)
    return {
        **_receipt_result(receipt),
        "idempotent_replay": False,
    }
