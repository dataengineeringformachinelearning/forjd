"""Integration-style security alert ingest → threat intel + SOC correlate.

From DEML integrations/api ingest_security_alert (no Django User / API-key table).
Auth is JWT membership on the tenant.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.services import playbooks as playbook_svc
from app.services import soc as soc_svc
from app.services import tenants as tenant_svc
from app.services import threat_intel as threat_svc
from app.services.correlation import evaluate_correlation_rules


# --- Adversarial / injection guards ---
def reject_ood_numeric(value: float) -> None:
    if value < -1000 or value > 1000:
        raise ValueError("numeric input outside allowed range [-1000, 1000]")


_PROMPT_INJECTION = (
    "ignore previous",
    "system prompt",
    "jailbreak",
    "select ",
    "drop ",
    "insert ",
    "delete ",
)


def reject_prompt_injection(prompt: str) -> None:
    lowered = prompt.lower()
    if any(token in lowered for token in _PROMPT_INJECTION):
        raise ValueError("prompt rejected by injection heuristic")


async def ingest_security_alert(
    pool: asyncpg.Pool,
    *,
    user: AuthUser,
    tenant_id: UUID,
    source: str,
    severity: str,
    title: str,
    ip_address: str | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_member(
        pool,
        tenant_id=tenant_id,
        user_id=user.user_id,
        min_roles=frozenset({"owner", "admin", "member"}),
    )
    await threat_svc.ensure_threat_schema(pool)
    is_malicious = severity.lower() in {"critical", "high"}
    abuse = 100 if is_malicious else 50
    row = await pool.fetchrow(
        """
        INSERT INTO threat_intelligence (
            tenant_id, is_platform, source, ip_address, location,
            abuse_confidence_score, is_malicious, raw_payload
        )
        VALUES (
            $1::uuid, FALSE, $2, $3::inet, $4, $5, $6, $7::jsonb
        )
        RETURNING id::text, source, host(ip_address) AS ip_address, is_malicious, created_at
        """,
        str(tenant_id),
        f"{source}_threat_intel",
        ip_address,
        title[:255],
        abuse,
        is_malicious,
        json.dumps(raw or {"title": title, "severity": severity}),
    )
    context = {
        "is_malicious": is_malicious,
        "abuse_confidence_score": abuse,
        "threat_match": is_malicious,
        "event_type": "security_alert",
        "source": source,
    }
    matches = evaluate_correlation_rules(context)
    case = None
    if matches:
        case = await soc_svc.open_case_from_context(
            pool, tenant_id=tenant_id, context=context, actor_id=user.user_id
        )
    playbooks = await playbook_svc.run_matching_playbooks(
        pool, tenant_id=tenant_id, context=context
    )
    return {
        "ok": True,
        "threat": dict(row),
        "matches": [m.rule_id for m in matches],
        "case": case,
        "playbooks": playbooks,
    }
