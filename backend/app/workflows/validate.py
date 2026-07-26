"""Validate workflow definitions for local DX / CI (YAML remains SoT).

Fail closed on parse errors and unknown processors/steps when ``strict=True``.
Runtime ingest still soft-skips unknown detectors unless ``WORKFLOWS_STRICT``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.workflows.detectors import REGISTRY as DETECTOR_REGISTRY
from app.workflows.loader import load_workflow_file
from app.workflows.models import WorkflowDefinition
from app.workflows.processors import REGISTRY as PROCESSOR_REGISTRY

# --- Built-in processor-local steps (not detectors) ---
_BUILTIN_STEPS = frozenset({"rollup"})


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    path: str
    level: str  # "error" | "warning"
    message: str


# --- Single definition ---
def validate_workflow_definition(
    wf: WorkflowDefinition,
    *,
    path: str = "<memory>",
    strict: bool = True,
) -> list[ValidationIssue]:
    """Check processor/steps/encryption against registered extension points."""
    issues: list[ValidationIssue] = []
    level = "error" if strict else "warning"

    if not wf.id.strip():
        issues.append(ValidationIssue(path, "error", "workflow id is empty"))

    proc = wf.pipeline.processor
    if proc not in PROCESSOR_REGISTRY:
        known = ", ".join(sorted(PROCESSOR_REGISTRY)) or "(none)"
        issues.append(
            ValidationIssue(
                path,
                level,
                f"unknown processor {proc!r}; known: {known}",
            )
        )

    for step in wf.pipeline.steps:
        if step in _BUILTIN_STEPS or step in DETECTOR_REGISTRY:
            continue
        known = ", ".join(sorted(_BUILTIN_STEPS | set(DETECTOR_REGISTRY))) or "(none)"
        issues.append(
            ValidationIssue(
                path,
                level,
                f"unknown step {step!r}; known: {known} "
                f"(custom detectors need REGISTRY + Rust parity — see docs/EXTENDING.md)",
            )
        )

    modes = {m.lower() for m in wf.encryption.modes}
    if modes and modes != {"e2ee"}:
        issues.append(
            ValidationIssue(
                path,
                "error",
                f"encryption.modes must be E2EE-only; got {sorted(modes)}",
            )
        )

    if not wf.match.content_types:
        issues.append(
            ValidationIssue(path, "error", "match.content_types must list at least one type")
        )

    if "rollup" not in wf.pipeline.steps:
        issues.append(
            ValidationIssue(
                path,
                "warning",
                "pipeline.steps omits rollup — sealed rollup usually runs first",
            )
        )

    return issues


# --- Directory / file scan ---
def validate_workflow_path(path: Path, *, strict: bool = True) -> list[ValidationIssue]:
    try:
        wf = load_workflow_file(path)
    except Exception as exc:  # noqa: BLE001 — surface parse errors to CLI
        return [ValidationIssue(str(path), "error", f"failed to load: {exc}")]
    return validate_workflow_definition(wf, path=str(path), strict=strict)


def iter_workflow_files(directory: Path, *, include_examples: bool = False) -> list[Path]:
    if not directory.is_dir():
        return []
    found: list[Path] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_dir():
            if include_examples and path.name == "examples":
                for child in sorted(path.iterdir()):
                    if child.suffix.lower() in {".yaml", ".yml", ".json"} and child.is_file():
                        found.append(child)
            continue
        if path.suffix.lower() in {".yaml", ".yml", ".json"}:
            found.append(path)
    return found


def validate_workflows_dir(
    directory: Path,
    *,
    include_examples: bool = False,
    strict: bool = True,
) -> list[ValidationIssue]:
    files = iter_workflow_files(directory, include_examples=include_examples)
    if not files:
        return [
            ValidationIssue(
                str(directory),
                "error",
                "no workflow YAML/JSON files found (set WORKFLOWS_DIR or pass --dir)",
            )
        ]

    issues: list[ValidationIssue] = []
    # examples/ is not loaded with top-level YAML — allow shared ids (alias overlays).
    seen_ids: dict[str, str] = {}
    for path in files:
        file_issues = validate_workflow_path(path, strict=strict)
        issues.extend(file_issues)
        if any(i.level == "error" and i.message.startswith("failed to load") for i in file_issues):
            continue
        if "examples" in path.parts:
            continue
        try:
            wf = load_workflow_file(path)
        except Exception:  # noqa: BLE001
            continue
        prior = seen_ids.get(wf.id)
        if prior is not None:
            issues.append(
                ValidationIssue(
                    str(path),
                    "error",
                    f"duplicate workflow id {wf.id!r} (also in {prior})",
                )
            )
        else:
            seen_ids[wf.id] = str(path)
    return issues


def issues_block_exit(issues: list[ValidationIssue]) -> bool:
    return any(i.level == "error" for i in issues)
