"""Security playbooks — trigger evaluation + ordered actions (webhook first)."""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import asyncpg
import httpx

from app.core.auth import AuthUser
from app.services import tenants as tenant_svc
from app.services.correlation import evaluate_playbook_trigger

logger = logging.getLogger("forjd.playbooks")


# --- Soft schema ---
async def ensure_playbook_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS playbooks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            trigger_conditions JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS playbook_actions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            playbook_id UUID NOT NULL REFERENCES playbooks (id) ON DELETE CASCADE,
            action_type TEXT NOT NULL,
            configuration JSONB NOT NULL DEFAULT '{}'::jsonb,
            sort_order INT NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


# --- CRUD ---
async def create_playbook(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    name: str,
    description: str = "",
    trigger_conditions: dict[str, Any] | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin"}),
    )
    await ensure_playbook_schema(pool)
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            """
            INSERT INTO playbooks (tenant_id, name, description, trigger_conditions)
            VALUES ($1::uuid, $2, $3, $4::jsonb)
            RETURNING id::text, tenant_id::text, name, description, is_active,
                      trigger_conditions, created_at, updated_at
            """,
            str(tenant_id),
            name.strip(),
            description,
            json.dumps(trigger_conditions or {}),
        )
        action_rows: list[dict[str, Any]] = []
        for i, action in enumerate(actions or []):
            arow = await conn.fetchrow(
                """
                INSERT INTO playbook_actions (playbook_id, action_type, configuration, sort_order)
                VALUES ($1::uuid, $2, $3::jsonb, $4)
                RETURNING id::text, action_type, configuration, sort_order
                """,
                row["id"],
                str(action["action_type"]),
                json.dumps(action.get("configuration") or {}),
                int(action.get("sort_order", i)),
            )
            action_rows.append(
                {
                    "id": arow["id"],
                    "action_type": arow["action_type"],
                    "configuration": arow["configuration"]
                    if isinstance(arow["configuration"], dict)
                    else {},
                    "sort_order": arow["sort_order"],
                }
            )
    out = _playbook_dict(row)
    out["actions"] = action_rows
    return out


async def list_playbooks(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
) -> list[dict[str, Any]]:
    await tenant_svc.require_member(pool, tenant_id=tenant_id, user_id=user.user_id)
    await ensure_playbook_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, tenant_id::text, name, description, is_active,
               trigger_conditions, created_at, updated_at
        FROM playbooks
        WHERE tenant_id = $1::uuid
        ORDER BY created_at DESC
        """,
        str(tenant_id),
    )
    return [_playbook_dict(r) for r in rows]


# --- Run matching playbooks for a context ---
async def run_matching_playbooks(
    pool: asyncpg.Pool,
    *,
    tenant_id: UUID,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    await ensure_playbook_schema(pool)
    rows = await pool.fetch(
        """
        SELECT id::text, name, is_active, trigger_conditions
        FROM playbooks
        WHERE tenant_id = $1::uuid AND is_active = TRUE
        """,
        str(tenant_id),
    )
    results: list[dict[str, Any]] = []
    for row in rows:
        conditions = row["trigger_conditions"]
        if isinstance(conditions, str):
            conditions = json.loads(conditions)
        if not evaluate_playbook_trigger(
            is_active=bool(row["is_active"]),
            trigger_conditions=conditions if isinstance(conditions, dict) else {},
            context=context,
        ):
            continue
        action_results = await _execute_actions(pool, playbook_id=row["id"], context=context)
        results.append(
            {
                "playbook_id": row["id"],
                "name": row["name"],
                "actions": action_results,
            }
        )
    return results


async def _execute_actions(
    pool: asyncpg.Pool,
    *,
    playbook_id: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    actions = await pool.fetch(
        """
        SELECT id::text, action_type, configuration
        FROM playbook_actions
        WHERE playbook_id = $1::uuid
        ORDER BY sort_order ASC
        """,
        playbook_id,
    )
    out: list[dict[str, Any]] = []
    for action in actions:
        cfg = action["configuration"]
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        if not isinstance(cfg, dict):
            cfg = {}
        action_type = str(action["action_type"])
        if action_type == "webhook":
            result = await _run_webhook(cfg, context)
        elif action_type in {"email_alert", "block_ip", "revoke_api_key"}:
            # Identity-side actions stay in DEML/Django; emit a request receipt only.
            result = {
                "ok": True,
                "deferred": True,
                "reason": "control_plane_action",
                "action_type": action_type,
            }
        else:
            result = {"ok": False, "error": f"unknown action_type {action_type}"}
        out.append({"action_id": action["id"], "action_type": action_type, **result})
    return out


async def _run_webhook(cfg: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    url = str(cfg.get("url") or "").strip()
    if not url.startswith(("https://", "http://")):
        return {"ok": False, "error": "invalid webhook url"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"context": context, "source": "forjd-playbook"})
        return {"ok": response.is_success, "status_code": response.status_code}
    except Exception as exc:  # noqa: BLE001
        logger.warning("playbook webhook failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def _playbook_dict(row: asyncpg.Record) -> dict[str, Any]:
    conditions = row["trigger_conditions"]
    if isinstance(conditions, str):
        conditions = json.loads(conditions)
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "name": row["name"],
        "description": row["description"],
        "is_active": bool(row["is_active"]),
        "trigger_conditions": conditions if isinstance(conditions, dict) else {},
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
