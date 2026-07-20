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

from app.services import audit
from app.services import service_accounts as sa_svc
from app.services import tenants as tenant_svc

logger = logging.getLogger("forjd.partner_provision")

_EXTERNAL_REF_RE = re.compile(r"^[a-z0-9][a-z0-9:_-]{3,127}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


async def ensure_partner_provision_schema(pool: asyncpg.Pool) -> None:
    await tenant_svc.ensure_secure_schema(pool)
    await sa_svc.ensure_schema(pool)
    await pool.execute(
        """
        CREATE TABLE IF NOT EXISTS partner_provisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            external_ref TEXT NOT NULL UNIQUE,
            partner TEXT NOT NULL DEFAULT 'deml',
            tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            service_account_id UUID NOT NULL REFERENCES service_accounts (id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _slug_for_external_ref(external_ref: str, *, explicit: str | None) -> str:
    if explicit:
        slug = explicit.strip().lower()
        if not _SLUG_RE.fullmatch(slug):
            raise ValueError("invalid slug")
        return slug
    digest = hashlib.sha256(external_ref.encode("utf-8")).hexdigest()[:12]
    return f"deml-{digest}"


def _name_for_external_ref(external_ref: str, *, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()[:128]
    return f"DEML {external_ref}"[:128]


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
    partner_key = (partner or "deml").strip().lower()[:64] or "deml"

    await ensure_partner_provision_schema(pool)

    existing = await pool.fetchrow(
        """
        SELECT id::text, tenant_id::text, service_account_id::text
        FROM partner_provisions
        WHERE external_ref = $1
        """,
        ref,
    )
    if existing is not None and not remint_if_exists:
        tenant = await pool.fetchrow(
            """
            SELECT id::text, slug, name, key_directory_id, created_at
            FROM tenants WHERE id = $1::uuid
            """,
            existing["tenant_id"],
        )
        sa = await pool.fetchrow(
            """
            SELECT id, tenant_id, name, subprocessor, prefix, auth_user_id,
                   scopes, is_active, revoked_at, created_by,
                   created_at, updated_at, last_used_at
            FROM service_accounts WHERE id = $1::uuid
            """,
            existing["service_account_id"],
        )
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

    tenant_slug = _slug_for_external_ref(ref, explicit=slug)
    tenant_name = _name_for_external_ref(ref, explicit=name)
    scopes = sa_svc._normalize_scopes(None, include_tenant_erase=include_tenant_erase)

    async with pool.acquire() as conn, conn.transaction():
        if existing is not None and remint_if_exists:
            tenant_id = str(existing["tenant_id"])
            # Revoke previous SA; mint a replacement under the same tenant.
            await conn.execute(
                """
                UPDATE service_accounts
                SET is_active = FALSE, revoked_at = NOW(), updated_at = NOW()
                WHERE id = $1::uuid AND revoked_at IS NULL
                """,
                existing["service_account_id"],
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
                SET service_account_id = $2::uuid, updated_at = NOW()
                WHERE external_ref = $1
                """,
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
        pool,
        action="partner.provision",
        actor_user_id=None,
        tenant_id=UUID(tenant_id),
        resource_type="partner_provision",
        resource_id=ref,
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
