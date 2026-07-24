"""Idempotent partner tenant + service-account provisioning for DEML BFF.

Authenticated only via ``FORJD_PROVISION_TOKEN`` (never tenant ``fjsvc_``).
Plaintext tokens are returned once on create/remint; never stored.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import settings
from app.services import audit
from app.services import service_accounts as sa_svc
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.partner_provision")

_EXTERNAL_REF_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{3,127}$")
_PARTNER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")

# Explicit DEML BFF contract. Keep generic service-account defaults unchanged.
DEML_PROVISION_SCOPES: tuple[str, ...] = (
    "ingest:write",
    "ingest:read",
    "projections:read",
    "projections:run",
    "sessions:write",
    "sessions:read",
    "replay:read",
    "replay:write",
    "status:read",
    "status:write",
    "analytics:read",
    "ml:read",
    "ml:write",
    "exports:read",
    "exports:write",
    "vulnerabilities:read",
    "vulnerabilities:write",
    "integrations:write",
    "siem:read",
    "siem:write",
    "cases:read",
    "cases:write",
    "playbooks:read",
    "playbooks:write",
    "playbooks:execute",
    "threat-intel:read",
    "reports:read",
    "reports:write",
)


async def ensure_partner_provision_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    if not settings.SOFT_MIGRATE_SCHEMA:
        return
    await sa_svc.ensure_schema(pool)
    await audit.ensure_audit_schema(pool)
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS service_accounts_id_tenant_uidx
        ON service_accounts (id, tenant_id)
        """
    )
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS partner_provisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            partner TEXT NOT NULL DEFAULT 'deml',
            external_ref TEXT NOT NULL,
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            service_account_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT partner_provisions_partner_format CHECK (
                partner = LOWER(BTRIM(partner))
                AND partner ~ '^[a-z0-9][a-z0-9_-]{0,63}$'
            ),
            CONSTRAINT partner_provisions_service_account_tenant_fkey
                FOREIGN KEY (service_account_id, tenant_id)
                REFERENCES service_accounts (id, tenant_id) ON DELETE CASCADE
        )
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS partner_provisions_partner_external_ref_uidx
        ON partner_provisions (partner, external_ref)
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS partner_provisions_tenant_uidx
        ON partner_provisions (tenant_id)
        """
    )
    await pool.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS partner_provisions_service_account_uidx
        ON partner_provisions (service_account_id)
        """
    )
    await pool.execute(
        """
        ALTER TABLE partner_provisions
        DROP CONSTRAINT IF EXISTS partner_provisions_external_ref_key
        """
    )


def _normalize_partner(partner: str) -> str:
    if not isinstance(partner, str):
        raise ValueError("invalid partner")
    key = partner.strip().lower()
    if not _PARTNER_RE.fullmatch(key):
        raise ValueError("invalid partner")
    return key


def _slug_for_external_ref(
    external_ref: str,
    *,
    partner: str = "deml",
    explicit: str | None,
) -> str:
    if explicit:
        slug = explicit.strip().lower()
        if not _SLUG_RE.fullmatch(slug):
            raise ValueError("invalid slug")
        return slug
    partner_key = _normalize_partner(partner)
    digest = hashlib.sha256(f"{partner_key}:{external_ref}".encode()).hexdigest()[:12]
    slug_prefix = partner_key.replace("_", "-")[:49]
    return f"{slug_prefix}-{digest}"


def _name_for_external_ref(
    external_ref: str,
    *,
    partner: str,
    explicit: str | None,
) -> str:
    if explicit and explicit.strip():
        return explicit.strip()[:128]
    return f"{partner.upper()} {external_ref}"[:128]


def _scopes_for_partner(partner: str, *, include_tenant_erase: bool) -> list[str]:
    partner_key = _normalize_partner(partner)
    configured = DEML_PROVISION_SCOPES if partner_key == "deml" else sa_svc.DEFAULT_SCOPES
    return sa_svc._normalize_scopes(
        list(configured),
        include_tenant_erase=include_tenant_erase,
    )


async def _existing_response(
    conn: asyncpg.Connection,
    existing: asyncpg.Record,
) -> dict[str, Any]:
    tenant = await conn.fetchrow(
        """
        SELECT id::text, slug, name, key_directory_id, created_at
        FROM tenants WHERE id = $1::uuid
        """,
        existing["tenant_id"],
    )
    sa = await conn.fetchrow(
        """
        SELECT id, tenant_id, name, subprocessor, prefix, auth_user_id,
               scopes, is_active, revoked_at, created_by,
               created_at, updated_at, last_used_at
        FROM service_accounts
        WHERE id = $1::uuid AND tenant_id = $2::uuid
        """,
        existing["service_account_id"],
        existing["tenant_id"],
    )
    if tenant is None or sa is None:
        raise RuntimeError("partner provision tenant integrity violation")
    return {
        "ok": True,
        "created": False,
        "reminted": False,
        "tenant": {
            "id": tenant["id"],
            "slug": tenant["slug"],
            "name": tenant["name"],
            "key_directory_id": tenant["key_directory_id"],
            "created_at": tenant["created_at"],
        },
        "service_account": {
            **sa_svc._public_row(sa),
            "token": None,
            "token_hint": "Token already issued; set remint_if_exists to rotate.",
        },
    }


async def provision_partner_tenant(
    pool: asyncpg.Pool,
    *,
    external_ref: str,
    partner: str = "deml",
    slug: str | None = None,
    name: str | None = None,
    include_tenant_erase: bool = True,
    remint_if_exists: bool = False,
) -> dict[str, Any]:
    """Create or return a partner-bound tenant + opaque service token."""
    ref = (external_ref or "").strip().lower()
    if not _EXTERNAL_REF_RE.fullmatch(ref):
        raise ValueError("invalid external_ref")
    partner_key = _normalize_partner(partner)

    await ensure_partner_provision_schema(pool)

    tenant_slug = _slug_for_external_ref(ref, partner=partner_key, explicit=slug)
    tenant_name = _name_for_external_ref(ref, partner=partner_key, explicit=name)
    scopes = _scopes_for_partner(
        partner_key,
        include_tenant_erase=include_tenant_erase,
    )

    async with pool.acquire() as conn, conn.transaction():
        await conn.fetchval(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            f"partner-provision:{partner_key}:{ref}",
        )
        existing = await conn.fetchrow(
            """
            SELECT id::text, tenant_id::text, service_account_id::text
            FROM partner_provisions
            WHERE partner = $1 AND external_ref = $2
            FOR UPDATE
            """,
            partner_key,
            ref,
        )
        if existing is not None and not remint_if_exists:
            return await _existing_response(conn, existing)

        if existing is not None and remint_if_exists:
            tenant_id = str(existing["tenant_id"])
            # Revoke previous SA; mint a replacement under the same tenant.
            await conn.execute(
                """
                UPDATE service_accounts
                SET is_active = FALSE, revoked_at = NOW(), updated_at = NOW()
                WHERE id = $1::uuid
                  AND tenant_id = $2::uuid
                  AND revoked_at IS NULL
                """,
                existing["service_account_id"],
                existing["tenant_id"],
            )
            created = False
            reminted = True
        else:
            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO tenants (slug, name)
                    VALUES ($1, $2)
                    RETURNING id::text, slug, name, key_directory_id, created_at
                    """,
                    tenant_slug,
                    tenant_name,
                )
            except asyncpg.UniqueViolationError as exc:
                raise ValueError("slug already taken") from exc
            tenant_id = row["id"]
            created = True
            reminted = False

        token, prefix, key_hash = sa_svc._mint_opaque_token()
        try:
            sa_row = await conn.fetchrow(
                """
                INSERT INTO service_accounts (
                    tenant_id, name, subprocessor, prefix, key_hash,
                    auth_user_id, scopes, created_by
                )
                VALUES (
                    $1::uuid, $2, $3, $4, $5,
                    NULL, $6::text[], NULL
                )
                RETURNING id, tenant_id, name, subprocessor, prefix, auth_user_id,
                          scopes, is_active, revoked_at, created_by,
                          created_at, updated_at, last_used_at
                """,
                tenant_id,
                f"{partner_key}-runtime"[:128],
                partner_key,
                prefix,
                key_hash,
                scopes,
            )
        except asyncpg.UniqueViolationError as exc:
            raise ValueError("service account conflict") from exc

        if existing is not None and remint_if_exists:
            await conn.execute(
                """
                UPDATE partner_provisions
                SET service_account_id = $3::uuid, updated_at = NOW()
                WHERE partner = $1 AND external_ref = $2
                """,
                partner_key,
                ref,
                str(sa_row["id"]),
            )
        else:
            await conn.execute(
                """
                INSERT INTO partner_provisions (
                    external_ref, partner, tenant_id, service_account_id
                )
                VALUES ($1, $2, $3::uuid, $4::uuid)
                """,
                ref,
                partner_key,
                tenant_id,
                str(sa_row["id"]),
            )

        tenant = await conn.fetchrow(
            """
            SELECT id::text, slug, name, key_directory_id, created_at
            FROM tenants WHERE id = $1::uuid
            """,
            tenant_id,
        )
        await audit.record_required(
            conn,
            action="partner.provision",
            actor_user_id=None,
            tenant_id=UUID(tenant_id),
            resource_type="partner_provision",
            resource_id=f"{partner_key}:{ref}",
            details={
                "partner": partner_key,
                "created": created,
                "reminted": reminted,
                "service_account_id": str(sa_row["id"]),
            },
        )

    out_sa = sa_svc._public_row(sa_row)
    out_sa["token"] = token
    out_sa["token_hint"] = "Store this token securely; it cannot be retrieved again."
    return {
        "ok": True,
        "created": created,
        "reminted": reminted,
        "tenant": {
            "id": tenant["id"],
            "slug": tenant["slug"],
            "name": tenant["name"],
            "key_directory_id": tenant["key_directory_id"],
            "created_at": tenant["created_at"],
        },
        "service_account": out_sa,
    }
