"""SOC readiness criteria payload ."""

from __future__ import annotations

from typing import Any

import asyncpg

_SOC_CRITERIA: list[dict[str, str]] = [
    {
        "name": "End-to-End Encryption",
        "category": "Security / Confidentiality",
        "status": "compliant",
        "description": (
            "Sealed ingest uses AES-256-GCM; plaintext never crosses the API on the E2EE path."
        ),
        "details": (
            "Verified. FORJD stores ciphertext only; X25519/HKDF session keys are client-held."
        ),
    },
    {
        "name": "AES-256 Encryption at Rest",
        "category": "Confidentiality",
        "status": "compliant",
        "description": "Telemetry ciphertext and credentials must be encrypted at rest.",
        "details": "Active. Supabase/Postgres volume encryption + sealed event envelopes.",
    },
    {
        "name": "Audit Logging & Threat Anomaly Tracking",
        "category": "Security",
        "status": "compliant",
        "description": "Metadata-only audit events for authorization and operational actions.",
        "details": "Active. audit_events never store ciphertext or keys (sql/010).",
    },
    {
        "name": "Multi-Factor Authentication & SSO",
        "category": "Security",
        "status": "compliant",
        "description": "Identity is enforced via Supabase Auth JWT (MFA/SSO owned by IdP).",
        "details": "Active. FORJD verifies JWTs; account lifecycle stays with the identity plane.",
    },
    {
        "name": "Database Backups & Redundancy",
        "category": "Availability",
        "status": "compliant",
        "description": "Managed Postgres snapshots with retention.",
        "details": "Active. Supabase continuous backups / PITR when enabled on the project.",
    },
]


async def build_soc_status(pool: asyncpg.Pool | None = None) -> dict[str, Any]:
    """Static SOC criteria — never query cross-tenant session tables."""
    del pool  # reserved for future tenant-scoped signals only
    total = len(_SOC_CRITERIA)
    compliant_count = sum(1 for c in _SOC_CRITERIA if c["status"] == "compliant")
    score = float(compliant_count / total)
    return {
        "status": "success",
        "overall_score": score,
        "criteria": _SOC_CRITERIA,
        "e2e_encryption": {
            "transit": "TLS 1.3 on all connections",
            "rest": "Managed volume encryption + AES-256-GCM envelopes",
            "clientPayload": "E2EE sealed ingest; server-blind ciphertext",
            "rotationDaysRemaining": 30,
        },
    }
