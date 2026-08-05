#!/usr/bin/env python3
"""
FORJD unified local tooling — doctor, quality gates, and clear failure hints.

Usage (from repo root):
  python scripts/forjd_tooling.py doctor
  python scripts/forjd_tooling.py bootstrap [-- …flags]
  python scripts/forjd_tooling.py verify
  python scripts/forjd_tooling.py quality [--fast|--full]
  python scripts/forjd_tooling.py validate-workflows [-- …flags]
  python scripts/forjd_tooling.py install-hooks
  python scripts/forjd_tooling.py api
  python scripts/forjd_tooling.py help

Or via root package.json: npm run bootstrap / doctor / verify / validate:workflows / quality / …
New developers: docs/START_HERE.md · docs/EXTENDING.md
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ENGINE = ROOT / "engine"


# --- Process helpers ---
def _rust_pin() -> str:
    try:
        content = (ENGINE / "rust-toolchain.toml").read_text(encoding="utf-8")
    except OSError:
        return "1.97.1"
    match = re.search(r'^\s*channel\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else "1.97.1"


@lru_cache(maxsize=1)
def _pinned_rust_env() -> dict[str, str]:
    """Prefer the repo's rustup toolchain even when Homebrew shadows its proxies."""
    rustup = shutil.which("rustup")
    if not rustup:
        return {}
    paths: dict[str, str] = {}
    for tool in ("cargo", "rustc"):
        result = subprocess.run(
            [rustup, "which", tool, "--toolchain", _rust_pin()],
            check=False,
            capture_output=True,
            text=True,
        )
        candidate = result.stdout.strip()
        if result.returncode != 0 or not candidate or not Path(candidate).is_file():
            return {}
        paths[tool.upper()] = candidate
    toolchain_bin = str(Path(paths["CARGO"]).parent)
    return {
        **paths,
        "PATH": os.pathsep.join(
            part for part in (toolchain_bin, os.environ.get("PATH", "")) if part
        ),
    }


class ToolError(RuntimeError):
    """User-facing tooling failure with recovery hints."""

    def __init__(self, message: str, hints: list[str] | None = None) -> None:
        super().__init__(message)
        self.hints = hints or []


def _print_fail(message: str, hints: list[str] | None = None) -> None:
    print(f"\n✗ {message}", file=sys.stderr)
    for hint in hints or []:
        print(f"  → {hint}", file=sys.stderr)
    print("", file=sys.stderr)


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> int:
    label = " ".join(cmd)
    print(f"\n→ {label}")
    executable = Path(cmd[0]).name if cmd else ""
    rust_env = (
        _pinned_rust_env() if executable in {"cargo", "maturin", "uv", "uvx"} else {}
    )
    merged = {**os.environ, **rust_env, **(env or {})}
    result = subprocess.run(cmd, cwd=cwd or ROOT, env=merged, check=False)
    if check and result.returncode != 0:
        raise ToolError(
            f"Command failed ({result.returncode}): {label}",
            hints=_hints_for_command(cmd, cwd),
        )
    return result.returncode


def _hints_for_command(cmd: list[str], cwd: Path | None) -> list[str]:
    joined = " ".join(cmd)
    hints: list[str] = []
    if "check_config_catalog" in joined:
        hints.extend(
            [
                "Catalog check needs the backend uv env + PyYAML:",
                "  uv run --no-sync --project backend python scripts/check_config_catalog.py",
            ]
        )
    elif "ruff" in joined:
        hints.append("Fix: cd backend && uv run --no-sync ruff check . --fix")
        hints.append("Format: cd backend && uv run --no-sync ruff format .")
    elif cmd and Path(cmd[0]).name.startswith("uv"):
        hints.extend(
            [
                "Engine needs rustc 1.97 (engine/rust-toolchain.toml).",
                "  cd engine && rustup install 1.97 && rustup override set 1.97",
                "Then: cd backend && uv sync --locked",
            ]
        )
    if "cargo" in joined:
        hints.append(
            "From engine/: rustup show && cargo test --features server,data-plane"
        )
    if cwd:
        hints.append(f"Working directory was: {cwd}")
    hints.append("See docs/DEV.md for common failures.")
    return hints


def _which(name: str) -> str | None:
    return shutil.which(name)


# --- doctor ---
def cmd_doctor(_: argparse.Namespace) -> None:
    print("FORJD doctor — local toolchain\n")
    rows: list[tuple[str, str, str]] = []

    def note(label: str, ok: bool, detail: str) -> None:
        mark = "OK" if ok else "MISSING"
        rows.append((label, mark, detail))

    uv = _which("uv")
    note("uv", bool(uv), uv or "Install: https://docs.astral.sh/uv/")

    rustc = _which("rustc")
    if rustc:
        ver = subprocess.run(
            ["rustc", "--version"], check=False, capture_output=True, text=True
        ).stdout.strip()
        # Pin is 1.97 — Homebrew 1.96 still “present” but maturin will fail.
        # Match "rustc 1.97.x" only (avoid substring false positives).
        parts = ver.split()
        rust_ver = parts[1] if len(parts) >= 2 else ""
        pin = _rust_pin()
        pin_ok = rust_ver == pin
        pinned_env = _pinned_rust_env()
        pinned_rustc = pinned_env.get("RUSTC")
        note(
            "rustc",
            pin_ok or bool(pinned_rustc),
            (
                ver
                if pin_ok
                else (
                    f"{pin} via rustup ({pinned_rustc}); PATH has {ver}, "
                    "tooling will select the pin"
                    if pinned_rustc
                    else f"{ver} — engine pin is {pin} (rustup install {pin})"
                )
            ),
        )
    else:
        note("rustc", False, f"Install Rust via rustup (engine needs {_rust_pin()})")

    cargo = _pinned_rust_env().get("CARGO") or _which("cargo")
    note("cargo", bool(cargo), cargo or "Install via rustup")

    note(
        "backend/.env",
        (BACKEND / ".env").is_file(),
        "present"
        if (BACKEND / ".env").is_file()
        else "cp backend/.env.example backend/.env",
    )
    deml_ui_css = BACKEND / "static" / "deml-ui.css"
    note(
        "deml-ui.css",
        deml_ui_css.is_file(),
        "ok" if deml_ui_css.is_file() else "npm run sync:deml-ui (sibling deml-ui or deml pkg)",
    )

    configured_ui = os.environ.get("FORJD_DEML_UI_ROOT")
    ui_root = Path(configured_ui) if configured_ui else ROOT.parent / "deml-ui"
    note(
        "deml-ui sibling",
        (ui_root / "dist" / "styles" / "deml-ui.css").is_file(),
        str(ui_root)
        if (ui_root / "dist" / "styles" / "deml-ui.css").is_file()
        else f"optional — set FORJD_DEML_UI_ROOT (looked at {ui_root})",
    )

    docker = _which("docker")
    if docker:
        dock_ok = (
            subprocess.run(
                ["docker", "info"],
                check=False,
                capture_output=True,
            ).returncode
            == 0
        )
        note(
            "docker",
            dock_ok,
            "daemon up" if dock_ok else "install/start Docker Desktop",
        )
    else:
        note(
            "docker",
            False,
            "optional for local-db — https://docs.docker.com/get-docker/",
        )

    workflows_dir = BACKEND / "workflows"
    yaml_count = (
        len(list(workflows_dir.glob("*.yaml"))) + len(list(workflows_dir.glob("*.yml")))
        if workflows_dir.is_dir()
        else 0
    )
    note(
        "workflows/",
        workflows_dir.is_dir() and yaml_count > 0,
        f"{yaml_count} YAML file(s) — npm run validate:workflows"
        if yaml_count
        else "missing backend/workflows/*.yaml — see docs/EXTENDING.md",
    )

    width = max(len(r[0]) for r in rows)
    for label, mark, detail in rows:
        print(f"  {label:<{width}}  [{mark}]  {detail}")

    hard_fail = any(
        mark == "MISSING" and label in {"uv", "rustc", "cargo"}
        for label, mark, _ in rows
    )
    print()
    if hard_fail:
        _print_fail(
            "Doctor found blocking gaps.",
            [
                "Install missing tools, then re-run: python scripts/forjd_tooling.py doctor",
                "See docs/DEV.md",
            ],
        )
        raise SystemExit(1)
    print("✓ Doctor finished — fix any MISSING rows before quality/dev.\n")


# --- quality ---
def cmd_quality(args: argparse.Namespace) -> None:
    stage = args.stage
    print(f"FORJD quality ({stage})")

    # Catalog check needs PyYAML from the backend env (not system Python).
    # --no-sync avoids rebuilding forjd-engine on every quality run.
    _run(
        [
            "uv",
            "run",
            "--no-sync",
            "--project",
            str(BACKEND),
            "python",
            str(ROOT / "scripts" / "check_config_catalog.py"),
        ],
        cwd=ROOT,
    )
    _run(
        [
            "uv",
            "run",
            "--no-sync",
            "--project",
            str(BACKEND),
            "python",
            str(ROOT / "scripts" / "validate_workflows.py"),
        ],
        cwd=ROOT,
    )

    if (BACKEND / "pyproject.toml").is_file():
        _run(["uv", "run", "--no-sync", "ruff", "check", "."], cwd=BACKEND)
        _run(["uv", "run", "--no-sync", "ruff", "format", "--check", "."], cwd=BACKEND)
        if stage == "full":
            _run(
                [
                    "uv",
                    "run",
                    "--no-sync",
                    "python",
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                ],
                cwd=BACKEND,
            )

    # Match CI: cargo fmt --all + clippy --no-default-features.
    if stage == "full" and (ENGINE / "Cargo.toml").is_file():
        _run(["cargo", "fmt", "--all", "--", "--check"], cwd=ENGINE)
        _run(
            [
                "cargo",
                "clippy",
                "--no-default-features",
                "--features",
                "server,data-plane",
                "--",
                "-D",
                "warnings",
            ],
            cwd=ENGINE,
        )
        _run(
            [
                "cargo",
                "test",
                "--no-default-features",
                "--features",
                "server,data-plane",
            ],
            cwd=ENGINE,
        )

    print("\n✓ Quality gates passed.\n")


def cmd_install_hooks(_: argparse.Namespace) -> None:
    script = ROOT / "scripts" / "install_hooks.sh"
    if not script.is_file():
        raise ToolError(f"Missing {script}")
    _run(["bash", str(script)], cwd=ROOT)


def cmd_bootstrap(args: argparse.Namespace) -> None:
    script = ROOT / "scripts" / "bootstrap_local.sh"
    if not script.is_file():
        raise ToolError(f"Missing {script}")
    cmd = ["bash", str(script), *list(args.bootstrap_args or [])]
    _run(cmd, cwd=ROOT)


def cmd_verify(_: argparse.Namespace) -> None:
    script = ROOT / "scripts" / "verify_local.sh"
    if not script.is_file():
        raise ToolError(f"Missing {script}")
    _run(["bash", str(script)], cwd=ROOT)


def cmd_validate_workflows(args: argparse.Namespace) -> None:
    script = ROOT / "scripts" / "validate_workflows.py"
    if not script.is_file():
        raise ToolError(f"Missing {script}")
    _run(
        [
            "uv",
            "run",
            "--no-sync",
            "--project",
            str(BACKEND),
            "python",
            str(script),
            *list(args.validate_args or []),
        ],
        cwd=ROOT,
    )


# --- api / web ---
def cmd_api(_: argparse.Namespace) -> None:
    if not (BACKEND / ".env").is_file():
        raise ToolError(
            "backend/.env missing",
            hints=["cp backend/.env.example backend/.env", "See docs/DEV.md"],
        )
    print("Starting API with reload (DEBUG from settings / uvicorn --reload)…")
    print("  http://127.0.0.1:8000/health  ·  /ready  ·  /api/v1/capabilities\n")
    # Prefer explicit reload for DX even when DEBUG is false in .env.
    os.environ.update(_pinned_rust_env())
    os.execvp(
        "uv",
        [
            "uv",
            "run",
            "uvicorn",
            "app.main:app",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
            "--reload-dir",
            "app",
        ],
    )


def cmd_help(_: argparse.Namespace) -> None:
    print(__doc__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FORJD unified local tooling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Docs: docs/START_HERE.md · docs/DEV.md",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check uv/Rust/.env/deml-ui paths").set_defaults(
        func=cmd_doctor
    )
    boot = sub.add_parser(
        "bootstrap",
        help="First-time local setup (env, Docker DB, uv sync, deml-ui sync)",
    )
    boot.add_argument(
        "bootstrap_args",
        nargs="*",
        help="Flags for bootstrap_local.sh (--skip-docker, --no-hooks)",
    )
    boot.set_defaults(func=cmd_bootstrap)
    sub.add_parser("verify", help="curl /health /ready /capabilities").set_defaults(
        func=cmd_verify
    )
    vw = sub.add_parser(
        "validate-workflows",
        help="Validate workflow YAML against schema + detector/processor registries",
    )
    vw.add_argument(
        "validate_args",
        nargs="*",
        help="Flags for validate_workflows.py (--include-examples, paths, …)",
    )
    vw.set_defaults(func=cmd_validate_workflows)
    sub.add_parser("help", help="Show usage").set_defaults(func=cmd_help)

    q = sub.add_parser("quality", help="Run local quality gates")
    q.add_argument(
        "--fast",
        dest="stage",
        action="store_const",
        const="fast",
        default="fast",
        help="Catalog + ruff (default)",
    )
    q.add_argument(
        "--full",
        dest="stage",
        action="store_const",
        const="full",
        help="Also backend tests, engine fmt/clippy/test (CI-aligned)",
    )
    q.set_defaults(func=cmd_quality)

    sub.add_parser(
        "install-hooks",
        help="Install git pre-commit hooks (ruff, catalog, engine fmt)",
    ).set_defaults(func=cmd_install_hooks)

    sub.add_parser("api", help="Run FastAPI with reload on :8000").set_defaults(
        func=cmd_api
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except ToolError as exc:
        _print_fail(str(exc), exc.hints)
        return 1
    except FileNotFoundError as exc:
        _print_fail(
            f"Executable not found: {exc.filename or exc}",
            [
                "Install the missing tool",
                "Re-run: python scripts/forjd_tooling.py doctor",
            ],
        )
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
