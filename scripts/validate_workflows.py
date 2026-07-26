#!/usr/bin/env python3
"""Validate FORJD workflow YAML/JSON (schema + processor/detector registries).

Run from repo root:

  npm run validate:workflows
  uv run --project backend python scripts/validate_workflows.py
  uv run --project backend python scripts/validate_workflows.py path/to/file.yaml
  uv run --project backend python scripts/validate_workflows.py --include-examples

Exit 0 when there are no errors. Warnings (e.g. missing rollup) do not fail
unless ``--strict-warnings`` is set. Unknown steps fail by default so typos
surface before deploy — runtime ingest still soft-skips unless WORKFLOWS_STRICT=1.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def _ensure_backend_path() -> None:
    backend = str(BACKEND)
    if backend not in sys.path:
        sys.path.insert(0, backend)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate FORJD workflow definitions")
    parser.add_argument(
        "paths",
        nargs="*",
        help="Optional YAML/JSON files (default: WORKFLOWS_DIR under backend/)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Workflows directory (default: backend/workflows or WORKFLOWS_DIR)",
    )
    parser.add_argument(
        "--include-examples",
        action="store_true",
        help="Also validate backend/workflows/examples/*.yaml (templates)",
    )
    parser.add_argument(
        "--soft",
        action="store_true",
        help="Treat unknown processors/steps as warnings (match runtime soft-skip)",
    )
    parser.add_argument(
        "--strict-warnings",
        action="store_true",
        help="Fail if any warning is present",
    )
    args = parser.parse_args(argv)

    _ensure_backend_path()
    os.chdir(BACKEND)

    from app.workflows.validate import (  # noqa: PLC0415 — after sys.path
        ValidationIssue,
        issues_block_exit,
        validate_workflow_path,
        validate_workflows_dir,
    )

    strict = not args.soft
    issues: list[ValidationIssue] = []

    if args.paths:
        for raw in args.paths:
            path = Path(raw)
            if not path.is_absolute():
                # Prefer CWD, then repo-relative.
                cand = Path.cwd() / path
                path = cand if cand.is_file() else (ROOT / raw)
            issues.extend(validate_workflow_path(path, strict=strict))
    else:
        directory = args.dir
        if directory is None:
            env_dir = os.environ.get("WORKFLOWS_DIR", "workflows")
            directory = Path(env_dir)
            if not directory.is_absolute():
                directory = BACKEND / directory
        issues.extend(
            validate_workflows_dir(
                directory,
                include_examples=args.include_examples,
                strict=strict,
            )
        )

    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]

    if not issues:
        print("✓ Workflows valid — no issues.")
        return 0

    for issue in issues:
        mark = "ERROR" if issue.level == "error" else "WARN "
        print(f"  [{mark}] {issue.path}: {issue.message}")

    print()
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    if issues_block_exit(issues) or (args.strict_warnings and warnings):
        print("See docs/EXTENDING.md · backend/workflows/README.md")
        return 1
    print("✓ Workflows valid (warnings only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
