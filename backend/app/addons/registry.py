"""Catalog of FORJD add-ons and the config gate that enables them.

An add-on is metadata + an optional capability probe. Registering one here does
**not** add a hard dependency: `kind` records how the integration ships
(`python` package, `service` client, `external_tool` binary, or `reference`
material) so slim images stay slim and disabled add-ons cost nothing.
"""

from __future__ import annotations

import importlib.util
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import yaml

from app.core.config import settings


# --- Taxonomy ---
class AddonKind(StrEnum):
    PYTHON = "python"  # importable Python package (optional dependency group)
    SERVICE = "service"  # remote API client (needs a URL / API key)
    EXTERNAL_TOOL = "external_tool"  # invokes a binary on PATH
    REFERENCE = "reference"  # docs / infra material, not a runtime dependency


class AddonCategory(StrEnum):
    VULNERABILITY = "vulnerability"
    THREAT_INTEL = "threat_intel"
    SCANNING = "scanning"
    ML = "ml"
    TESTING = "testing"
    REFERENCE = "reference"


@dataclass(frozen=True)
class Addon:
    """One optional integration. Disabled unless enabled via settings."""

    slug: str
    name: str
    category: AddonCategory
    kind: AddonKind
    summary: str
    source_url: str
    # Import name (PYTHON), binary name (EXTERNAL_TOOL), or settings attr (SERVICE).
    probe: str | None = None
    # Optional uv dependency group that installs this add-on's package.
    dependency_group: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)

    def available(self) -> bool:
        """True when the underlying package / binary / config is actually present.

        Availability is independent of enablement: an add-on can be enabled but
        not yet installed (reported so operators know what to provision).
        """
        if self.kind is AddonKind.PYTHON and self.probe:
            return importlib.util.find_spec(self.probe) is not None
        if self.kind is AddonKind.EXTERNAL_TOOL and self.probe:
            return shutil.which(self.probe) is not None
        if self.kind is AddonKind.SERVICE and self.probe:
            return bool(str(getattr(settings, self.probe, "") or "").strip())
        # Reference material is always "available" (nothing to install).
        return self.kind is AddonKind.REFERENCE


# --- Catalog (order = display order) ---
ADDONS: tuple[Addon, ...] = (
    Addon(
        slug="osv-dev",
        name="OSV.dev",
        category=AddonCategory.VULNERABILITY,
        kind=AddonKind.SERVICE,
        summary="Query the OSV.dev API to enrich the vulnerability ledger with "
        "known advisories for a package/version.",
        source_url="https://github.com/google/osv.dev",
        probe="OSV_API_URL",
        tags=("cve", "advisories", "enrichment"),
    ),
    Addon(
        slug="osv-scanner",
        name="OSV-Scanner",
        category=AddonCategory.VULNERABILITY,
        kind=AddonKind.EXTERNAL_TOOL,
        summary="Scan a lockfile / SBOM / directory for known vulnerabilities "
        "using Google's osv-scanner binary.",
        source_url="https://github.com/google/osv-scanner",
        probe="osv-scanner",
        tags=("sbom", "lockfile", "cve"),
    ),
    Addon(
        slug="osv-scalibr",
        name="OSV-SCALIBR",
        category=AddonCategory.SCANNING,
        kind=AddonKind.EXTERNAL_TOOL,
        summary="Extract software inventory (SBOM) from filesystems and "
        "container images with the scalibr binary.",
        source_url="https://github.com/google/osv-scalibr",
        probe="scalibr",
        tags=("sbom", "inventory"),
    ),
    Addon(
        slug="nuclei",
        name="Nuclei",
        category=AddonCategory.SCANNING,
        kind=AddonKind.EXTERNAL_TOOL,
        summary="Template-based vulnerability scanner (ProjectDiscovery) for "
        "domain-scanner findings.",
        source_url="https://github.com/projectdiscovery/nuclei",
        probe="nuclei",
        tags=("dast", "templates", "scanner"),
    ),
    Addon(
        slug="honeydb",
        name="HoneyDB",
        category=AddonCategory.THREAT_INTEL,
        kind=AddonKind.SERVICE,
        summary="Pull honeypot threat intelligence (bad hosts, activity) from "
        "the HoneyDB API into the threat-intel pipeline.",
        source_url="https://github.com/honeydbio/honeydb-python",
        probe="HONEYDB_API_ID",
        tags=("honeypot", "bad-hosts", "threat"),
    ),
    Addon(
        slug="go-cve-dictionary",
        name="go-cve-dictionary",
        category=AddonCategory.VULNERABILITY,
        kind=AddonKind.SERVICE,
        summary="Local CVE dictionary service (NVD/JVN mirror) queried over "
        "HTTP to enrich vulnerability records.",
        source_url="https://github.com/vulsio/go-cve-dictionary",
        probe="GO_CVE_DICTIONARY_URL",
        tags=("cve", "nvd", "mirror"),
    ),
    Addon(
        slug="jax",
        name="JAX",
        category=AddonCategory.ML,
        kind=AddonKind.PYTHON,
        summary="Accelerated array/autodiff stack for experimental ML detectors "
        "(install on demand; heavy).",
        source_url="https://github.com/jax-ml/jax",
        probe="jax",
        dependency_group="ml-jax",
        tags=("autodiff", "accelerator", "experimental"),
    ),
    Addon(
        slug="acme",
        name="DeepMind Acme",
        category=AddonCategory.ML,
        kind=AddonKind.PYTHON,
        summary="Reinforcement-learning research framework. Descriptor only — "
        "no FORJD runtime use case; install on demand for experiments.",
        source_url="https://github.com/google-deepmind/acme",
        probe="acme",
        dependency_group="ml-rl",
        tags=("reinforcement-learning", "research"),
    ),
    Addon(
        slug="robotframework",
        name="Robot Framework",
        category=AddonCategory.TESTING,
        kind=AddonKind.PYTHON,
        summary="Keyword-driven acceptance-test automation. Dev/CI add-on for "
        "end-to-end suites, not a runtime dependency.",
        source_url="https://github.com/robotframework/robotframework",
        probe="robot",
        dependency_group="test-acceptance",
        tags=("acceptance-tests", "dev"),
    ),
    Addon(
        slug="oss-fuzz",
        name="OSS-Fuzz",
        category=AddonCategory.TESTING,
        kind=AddonKind.REFERENCE,
        summary="Continuous fuzzing infrastructure. CI/infra integration only — "
        "wire the engine's fuzz targets into an OSS-Fuzz project.",
        source_url="https://github.com/ShielderSec/oss-fuzz",
        tags=("fuzzing", "ci", "infra"),
    ),
    Addon(
        slug="design-patterns-python",
        name="Design Patterns (Python)",
        category=AddonCategory.REFERENCE,
        kind=AddonKind.REFERENCE,
        summary="Reference catalog of Python design patterns. Educational "
        "material for contributors; not an installable dependency.",
        source_url="https://github.com/RefactoringGuru/design-patterns-python",
        tags=("reference", "education"),
    ),
)

_ADDONS_BY_SLUG: dict[str, Addon] = {a.slug: a for a in ADDONS}


# --- Enablement gate (settings.ADDONS_ENABLED / FORJD_ADDONS) ---
def _configured_slugs() -> set[str]:
    """Resolve enablement from env, then YAML; ``all`` enables the catalog.

    ``FORJD_ADDONS`` deliberately wins when non-empty, which makes one-off
    deployment overrides predictable. YAML accepts either ``enabled: [...]``
    or ``addons: {enabled: [...]}``.
    """
    raw = [s.strip().lower() for s in settings.ADDONS_ENABLED if s and s.strip()]
    if not raw and settings.FORJD_ADDONS_CONFIG.strip():
        path = Path(settings.FORJD_ADDONS_CONFIG).expanduser()
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(document, dict):
            raise ValueError(f"add-on config root must be a mapping: {path}")
        section = document.get("addons", document)
        if not isinstance(section, dict):
            raise ValueError(f"add-on config 'addons' must be a mapping: {path}")
        enabled = section.get("enabled", [])
        if isinstance(enabled, str):
            enabled = enabled.split(",")
        if not isinstance(enabled, list):
            raise ValueError(f"add-on config 'enabled' must be a list or string: {path}")
        raw = [str(s).strip().lower() for s in enabled if str(s).strip()]
    if "all" in raw:
        return set(_ADDONS_BY_SLUG)
    return {slug for slug in raw if slug in _ADDONS_BY_SLUG}


def enabled_addons() -> tuple[Addon, ...]:
    slugs = _configured_slugs()
    return tuple(a for a in ADDONS if a.slug in slugs)


def addon_enabled(slug: str) -> bool:
    return slug.strip().lower() in _configured_slugs()


def get_addon(slug: str) -> Addon | None:
    return _ADDONS_BY_SLUG.get(slug.strip().lower())


def catalog(only_enabled: bool = False) -> Iterable[Addon]:
    return enabled_addons() if only_enabled else ADDONS
