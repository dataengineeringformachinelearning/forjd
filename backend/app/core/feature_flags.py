"""Typed feature-flag view over ``Settings`` — runtime SoT for gates.

Inventory / docs SoT: ``config/forjd.catalog.yaml`` (see ``docs/CONFIGURATION.md``).
Do not invent a second flag system; empty tokens and ``0`` intervals remain the
disable pattern for optional integrations and workers.

ADR: ``docs/adr/0004-config-catalog-inventory-sot.md``,
``docs/adr/0007-sole-rate-limiter-and-addons.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, settings


@dataclass(frozen=True, slots=True)
class FeatureFlags:
    """Resolved, read-only gates derived from process settings."""

    # --- Add-ons ---
    addons_raw: str
    addons_all: bool
    addons_slugs: tuple[str, ...]

    # --- API surface ---
    api_docs_enabled: bool
    rate_limit_enabled: bool

    # --- Zero-trust ---
    soft_migrate_schema: bool
    require_rls: bool
    require_crypto_session: bool
    supabase_auth_required: bool

    # --- Worker enables (interval/tick > 0) ---
    analytics_worker_enabled: bool
    training_worker_enabled: bool
    retention_worker_enabled: bool
    projection_tick_enabled: bool

    def addon_enabled(self, slug: str) -> bool:
        """True when ``FORJD_ADDONS=all`` or the slug is listed."""
        if self.addons_all:
            return True
        return slug.strip().lower() in {s.lower() for s in self.addons_slugs}


def resolve_feature_flags(cfg: Settings | None = None) -> FeatureFlags:
    """Build feature flags from settings (defaults to process singleton)."""
    s = cfg if cfg is not None else settings
    raw = (s.FORJD_ADDONS or "").strip()
    slugs = tuple(s.ADDONS_ENABLED)
    return FeatureFlags(
        addons_raw=raw,
        addons_all=raw.lower() == "all",
        addons_slugs=slugs,
        api_docs_enabled=bool(s.ENABLE_API_DOCS),
        rate_limit_enabled=bool(s.RATE_LIMIT_ENABLED),
        soft_migrate_schema=bool(s.SOFT_MIGRATE_SCHEMA),
        require_rls=bool(s.REQUIRE_RLS),
        require_crypto_session=bool(s.REQUIRE_CRYPTO_SESSION),
        supabase_auth_required=bool(s.SUPABASE_AUTH_REQUIRED),
        analytics_worker_enabled=s.ANALYTICS_ROLLUP_INTERVAL_SECONDS > 0,
        training_worker_enabled=s.TRAINING_TICK_SECONDS > 0,
        retention_worker_enabled=s.RETENTION_SWEEP_INTERVAL_SECONDS > 0,
        projection_tick_enabled=s.PROJECTION_TICK_SECONDS > 0,
    )
