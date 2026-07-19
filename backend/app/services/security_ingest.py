"""Integration-style security alert ingest → threat intel + SOC correlate.

Security-alert ingest (no end-user identity table).
Auth is JWT membership on the tenant.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.core.auth import AuthUser
from app.models.siem import CreateSecuritySignalRequest
from app.services import siem as siem_svc
from app.services import tenants as tenant_svc


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
    client_alert_id: str,
    observed_at: datetime,
    source: str,
    severity: str,
    title: str,
    ip_address: str | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await tenant_svc.require_tenant_access(
        pool,
        principal=user,
        tenant_id=tenant_id,
        min_roles=frozenset({"owner", "admin", "member"}),
        required_scopes=frozenset({"integrations:write"}),
    )
    normalized = raw or {}
    is_malicious = severity.lower() in {"critical", "high"} or (
        normalized.get("is_malicious") is True
    )
    raw_abuse = normalized.get("abuse_confidence_score")
    requested_abuse = (
        int(raw_abuse)
        if isinstance(raw_abuse, (int, float)) and not isinstance(raw_abuse, bool)
        else (100 if is_malicious else 50)
    )
    raw_anomaly = normalized.get("anomaly_score")
    anomaly_score = (
        float(raw_anomaly)
        if isinstance(raw_anomaly, (int, float)) and not isinstance(raw_anomaly, bool)
        else 0.0
    )
    abuse = max(
        0,
        min(requested_abuse, 100),
    )
    metadata = {
        **normalized,
        "is_malicious": is_malicious,
        "threat_match": normalized.get("threat_match") is True or is_malicious,
        "abuse_confidence_score": abuse,
        "anomaly_score": anomaly_score,
    }
    signal = CreateSecuritySignalRequest.model_validate(
        {
            "tenant_id": tenant_id,
            "client_signal_id": f"security-alert:{client_alert_id}",
            "observed_at": observed_at,
            "source": source,
            "category": "threat_intelligence",
            "signal_type": "integration.security_alert",
            "severity": severity,
            "title": title,
            "summary": "Legacy integration alert normalized into the SIEM signal lane",
            "confidence": abuse,
            "observables": (
                [{"type": "ipv4" if "." in ip_address else "ipv6", "value": ip_address}]
                if ip_address
                else []
            ),
            "metadata": metadata,
            "correlate": True,
            "run_playbooks": True,
        }
    )
    result = await siem_svc.create_signal(pool, user=user, signal=signal)
    return {
        "ok": True,
        "deprecated_contract": True,
        "duplicate": result["duplicate"],
        "signal": result["signal"],
        # Compatibility aliases for callers migrating to /siem/signals.
        "threat": result["signal"],
        "matches": [item["rule_id"] for item in result["matches"]],
        "case": result["case"],
        "playbooks": result["playbook_runs"],
    }
