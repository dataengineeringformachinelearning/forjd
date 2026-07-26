#!/usr/bin/env python3
"""Enforce config/forjd.catalog.yaml as the inventory source of truth.

Checks:
  1. Every backend Settings field is listed in the catalog (settings: true).
  2. Every catalog settings:true name exists on Settings.
  3. Keys in backend/.env.example and engine/.env.example are catalogued.
  4. Catalog entries with example: … appear in that file.
  5. Frontend environment*.ts keys match the frontend catalog set.
  6. feature_flags names exist in the variables inventory.

Exit 0 on success; print a report and exit 1 on drift.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - CI uses backend uv env
    print("PyYAML required — run via: uv run --project backend python scripts/check_config_catalog.py")
    sys.exit(2)

# --- Paths ---
ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "config" / "forjd.catalog.yaml"
SETTINGS_PATH = ROOT / "backend" / "app" / "core" / "config.py"
BACKEND_ENV = ROOT / "backend" / ".env.example"
ENGINE_ENV = ROOT / "engine" / ".env.example"
FRONTEND_ENVS = (
    ROOT / "frontend" / "src" / "environments" / "environment.ts",
    ROOT / "frontend" / "src" / "environments" / "environment.development.ts",
)

ENV_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
FRONTEND_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")


# --- Parsers ---
def load_catalog() -> dict:
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"catalog must be a mapping: {CATALOG_PATH}")
    return data


def settings_field_names() -> set[str]:
    """Parse Settings class annotations from config.py without importing the app."""
    tree = ast.parse(SETTINGS_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            names: set[str] = set()
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    names.add(item.target.id)
            return names
    raise SystemExit(f"Settings class not found in {SETTINGS_PATH}")


def env_example_keys(path: Path, *, include_commented: bool = False) -> set[str]:
    """Parse dotenv keys. Optionally treat ``# KEY=`` as documented."""
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            if not include_commented:
                continue
            stripped = stripped.lstrip("#").strip()
        match = ENV_KEY_RE.match(stripped)
        if match:
            keys.add(match.group(1))
    return keys


def frontend_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    in_object = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if "export const environment" in line:
            in_object = True
            continue
        if in_object:
            if line.strip().startswith("};"):
                break
            match = FRONTEND_KEY_RE.match(line)
            if match:
                keys.add(match.group(1))
    return keys


# --- Checks ---
def main() -> int:
    catalog = load_catalog()
    variables = catalog.get("variables") or []
    flags = catalog.get("feature_flags") or []
    if not isinstance(variables, list) or not variables:
        print("ERROR: catalog.variables must be a non-empty list")
        return 1

    by_name: dict[str, dict] = {}
    errors: list[str] = []

    for entry in variables:
        if not isinstance(entry, dict) or "name" not in entry:
            errors.append(f"invalid variable entry: {entry!r}")
            continue
        name = str(entry["name"])
        if name in by_name:
            errors.append(f"duplicate catalog variable: {name}")
        by_name[name] = entry

    settings_names = settings_field_names()
    catalog_settings = {n for n, e in by_name.items() if e.get("settings") is True}

    missing_in_catalog = sorted(settings_names - catalog_settings)
    if missing_in_catalog:
        errors.append(
            "Settings fields missing from catalog (settings: true): "
            + ", ".join(missing_in_catalog)
        )

    extra_settings = sorted(catalog_settings - settings_names)
    if extra_settings:
        errors.append(
            "catalog settings:true not on Settings: " + ", ".join(extra_settings)
        )

    # --- .env.example coverage ---
    for path, layer in ((BACKEND_ENV, "backend"), (ENGINE_ENV, "engine")):
        active_keys = env_example_keys(path, include_commented=False)
        documented_keys = env_example_keys(path, include_commented=True)
        for key in sorted(active_keys):
            entry = by_name.get(key)
            if entry is None:
                errors.append(f"{path.relative_to(ROOT)} key not in catalog: {key}")
                continue
            layers = entry.get("layers") or []
            if layer not in layers:
                errors.append(
                    f"{path.relative_to(ROOT)} key {key} catalogued but layers "
                    f"missing {layer!r} (have {layers})"
                )

        for name, entry in by_name.items():
            example = entry.get("example")
            if not example:
                continue
            rel = Path(example)
            if rel != path.relative_to(ROOT):
                continue
            if str(example).endswith(".ts"):
                continue
            if name not in documented_keys:
                errors.append(
                    f"catalog {name} claims example {example} but key missing there"
                )

    # --- Frontend keys ---
    frontend_catalog = {n for n, e in by_name.items() if "frontend" in (e.get("layers") or [])}
    for path in FRONTEND_ENVS:
        keys = frontend_keys(path)
        if keys != frontend_catalog:
            only_file = sorted(keys - frontend_catalog)
            only_cat = sorted(frontend_catalog - keys)
            if only_file:
                errors.append(
                    f"{path.relative_to(ROOT)} keys not in catalog: "
                    + ", ".join(only_file)
                )
            if only_cat:
                errors.append(
                    f"catalog frontend keys missing from {path.relative_to(ROOT)}: "
                    + ", ".join(only_cat)
                )

    # --- Feature flag names must be inventory entries ---
    for flag in flags:
        if not isinstance(flag, dict) or "name" not in flag:
            errors.append(f"invalid feature_flags entry: {flag!r}")
            continue
        name = str(flag["name"])
        if name not in by_name:
            errors.append(f"feature_flags name not in variables: {name}")

    if errors:
        print(f"Config catalog drift ({len(errors)}):")
        for err in errors:
            print(f"  - {err}")
        print(f"\nUpdate {CATALOG_PATH.relative_to(ROOT)} and matching examples.")
        return 1

    print(
        f"OK config catalog — {len(by_name)} variables, "
        f"{len(flags)} feature flags, "
        f"{len(settings_names)} Settings fields"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
