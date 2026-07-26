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
  python scripts/forjd_tooling.py web
  python scripts/forjd_tooling.py help

Or via root package.json: npm run bootstrap / doctor / verify / validate:workflows / quality / …
New developers: docs/START_HERE.md · docs/EXTENDING.md
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ENGINE = ROOT / "engine"


# --- Process helpers ---
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
    merged = {**os.environ, **(env or {})}
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
    elif "npm" in joined or "ng " in joined or joined.rstrip().endswith(" ng"):
        hints.extend(
            [
                "Node ^22.22.3 || ^24.15+ required (frontend/.nvmrc).",
                "From frontend/: npm install && npm run preflight",
            ]
        )
    if "cargo" in joined:
        hints.append("From engine/: rustup show && cargo test --features server,data-plane")
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

    node = _which("node")
    if node:
        ver = subprocess.run(
            ["node", "-v"], check=False, capture_output=True, text=True
        ).stdout.strip()
        major_minor = ver.lstrip("v").split(".")
        ok = False
        if len(major_minor) >= 2:
            major, minor = int(major_minor[0]), int(major_minor[1])
            ok = (major == 22 and minor >= 22) or (major == 24 and minor >= 15) or major >= 26
        note("node", ok, f"{ver} ({node})" if ok else f"{ver} — need ^22.22.3 / ^24.15+")
    else:
        note("node", False, "Install Node 24 (see frontend/.nvmrc)")

    rustc = _which("rustc")
    if rustc:
        ver = subprocess.run(
            ["rustc", "--version"], check=False, capture_output=True, text=True
        ).stdout.strip()
        # Pin is 1.97 — Homebrew 1.96 still “present” but maturin will fail.
        # Match "rustc 1.97.x" only (avoid substring false positives).
        parts = ver.split()
        rust_ver = parts[1] if len(parts) >= 2 else ""
        pin_ok = rust_ver.startswith("1.97.")
        note(
            "rustc",
            True,
            ver if pin_ok else f"{ver} — engine pin is 1.97 (rustup install 1.97)",
        )
    else:
        note("rustc", False, "Install Rust via rustup (engine needs 1.97)")

    cargo = _which("cargo")
    note("cargo", bool(cargo), cargo or "Install via rustup")

    note(
        "backend/.env",
        (BACKEND / ".env").is_file(),
        "present" if (BACKEND / ".env").is_file() else "cp backend/.env.example backend/.env",
    )
    note(
        "frontend/node_modules",
        (FRONTEND / "node_modules" / "@angular" / "cli").is_dir(),
        "ok" if (FRONTEND / "node_modules" / "@angular" / "cli").is_dir() else "cd frontend && npm install",
    )
    note(
        "suite-tokens.css",
        (FRONTEND / "libs/forjd-ui/src/lib/styles/suite-tokens.css").is_file(),
        "ok" if (FRONTEND / "libs/forjd-ui/src/lib/styles/suite-tokens.css").is_file() else "cd frontend && npm run sync:suite",
    )

    deml = Path(
        os.environ.get("FORJD_DEML_ROOT")
        or os.environ.get("DEML_ROOT")
        or (ROOT.parent / "dataengineeringformachinelearning")
    )
    note(
        "DEML sibling",
        (deml / "packages/viking-ui/src/tokens").is_dir(),
        str(deml) if (deml / "packages/viking-ui/src/tokens").is_dir() else f"optional — set FORJD_DEML_ROOT (looked at {deml})",
    )

    docker = _which("docker")
    if docker:
        dock_ok = subprocess.run(
            ["docker", "info"],
            check=False,
            capture_output=True,
        ).returncode == 0
        note("docker", dock_ok, "daemon up" if dock_ok else "install/start Docker Desktop")
    else:
        note("docker", False, "optional for local-db — https://docs.docker.com/get-docker/")

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

    hard_fail = any(mark == "MISSING" and label in {"uv", "node", "cargo"} for label, mark, _ in rows)
    print()
    if hard_fail:
        _print_fail(
            "Doctor found blocking gaps.",
            ["Install missing tools, then re-run: python scripts/forjd_tooling.py doctor", "See docs/DEV.md"],
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

    if (FRONTEND / "package.json").is_file():
        _run(["npm", "run", "preflight"], cwd=FRONTEND)
        _run(["npm", "run", "format:check"], cwd=FRONTEND)
        _run(["npm", "run", "typecheck"], cwd=FRONTEND)
        _run(["npm", "run", "suite:purity"], cwd=FRONTEND)
        if stage == "full":
            _run(["npm", "run", "test:all"], cwd=FRONTEND)
            _run(["npm", "run", "build"], cwd=FRONTEND)

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


def cmd_web(_: argparse.Namespace) -> None:
    print("Starting Angular landing…")
    print("  http://127.0.0.1:4200\n")
    os.chdir(FRONTEND)
    os.execvp("npm", ["npm", "start"])


def cmd_help(_: argparse.Namespace) -> None:
    print(__doc__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FORJD unified local tooling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Docs: docs/START_HERE.md · docs/DEV.md",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check Node/uv/Rust/.env/suite paths").set_defaults(
        func=cmd_doctor
    )
    boot = sub.add_parser(
        "bootstrap",
        help="First-time local setup (env, Docker DB, uv sync, npm install)",
    )
    boot.add_argument(
        "bootstrap_args",
        nargs="*",
        help="Flags for bootstrap_local.sh (--frontend-only, --skip-docker, --no-hooks)",
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
        help="Catalog + ruff + prettier + typecheck + suite purity (default)",
    )
    q.add_argument(
        "--full",
        dest="stage",
        action="store_const",
        const="full",
        help="Also backend tests, engine fmt/clippy/test (CI-aligned), frontend tests + build",
    )
    q.set_defaults(func=cmd_quality)

    sub.add_parser(
        "install-hooks",
        help="Install git pre-commit hooks (ruff, prettier, typecheck)",
    ).set_defaults(func=cmd_install_hooks)

    sub.add_parser("api", help="Run FastAPI with reload on :8000").set_defaults(func=cmd_api)
    sub.add_parser("web", help="Run Angular landing on :4200").set_defaults(func=cmd_web)
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
            ["Install the missing tool", "Re-run: python scripts/forjd_tooling.py doctor"],
        )
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
