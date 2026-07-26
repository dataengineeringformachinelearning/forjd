#!/usr/bin/env python3
"""
Validate FORJD commit messages (Conventional Commits + hygiene).

Usage:
  python3 scripts/check_commit_msg.py <path-to-COMMIT_EDITMSG>
  echo 'feat(backend): add lease' | python3 scripts/check_commit_msg.py
  python3 scripts/check_commit_msg.py --self-test

See docs/GIT.md.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# --- Conventions (keep in sync with docs/GIT.md) ---
TYPES = (
    "feat",
    "fix",
    "docs",
    "refactor",
    "test",
    "chore",
    "perf",
    "ci",
    "build",
    "style",
    "revert",
)
TYPE_ALT = "|".join(TYPES)
# type(scope)!: subject  — scope optional; subject non-empty
CONVENTIONAL = re.compile(
    rf"^(?P<type>{TYPE_ALT})"
    r"(?:\((?P<scope>[a-z0-9][a-z0-9/_-]{0,32})\))?"
    r"(?P<breaking>!)?"
    r": "
    r"(?P<subject>.+)$"
)
SUBJECT_MAX = 72
NOISE = re.compile(
    r"^(wip|tmp|temp|asdf|test|updates?|misc|stuff|fix|checkpoint)\.?$",
    re.IGNORECASE,
)
PAST_TENSE = re.compile(
    r"^(added|fixed|updated|changed|removed|deleted|refactored|improved)\b",
    re.IGNORECASE,
)


# --- Parse / allowlist ---
def _subject_line(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        return line
    return ""


def _is_git_generated(subject: str) -> bool:
    lowered = subject.lower()
    return (
        lowered.startswith("merge ")
        or lowered.startswith("revert ")
        or lowered.startswith("fixup!")
        or lowered.startswith("squash!")
    )


# --- Validation ---
def validate_commit_message(text: str) -> list[str]:
    """Return a list of error strings (empty means OK)."""
    errors: list[str] = []
    subject = _subject_line(text)
    if not subject:
        return ["Commit message is empty."]

    if _is_git_generated(subject):
        return []

    if len(subject) > SUBJECT_MAX:
        errors.append(f"Subject is {len(subject)} chars (max {SUBJECT_MAX}).")

    match = CONVENTIONAL.match(subject)
    if not match:
        errors.append(
            "Use Conventional Commits: "
            f"<type>(optional-scope): <imperative subject>\n"
            f"  types: {', '.join(TYPES)}\n"
            "  example: feat(engine): scale workers with advisory leases\n"
            "  see docs/GIT.md"
        )
        return errors

    body_subject = match.group("subject").strip()
    if not body_subject:
        errors.append("Subject text after ': ' must not be empty.")
    if body_subject.endswith("."):
        errors.append("Do not end the subject with a period.")
    if NOISE.match(body_subject):
        errors.append(f"Subject is too vague: {body_subject!r}.")
    if PAST_TENSE.match(body_subject):
        errors.append(
            "Use imperative mood (e.g. 'add lease', not 'added lease')."
        )

    # Blank line required between subject and body when body exists.
    nonempty_idxs = [
        i
        for i, ln in enumerate(text.splitlines())
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if len(nonempty_idxs) >= 2:
        first, second = nonempty_idxs[0], nonempty_idxs[1]
        if second == first + 1:
            errors.append("Separate subject and body with a blank line.")

    return errors


# --- CLI ---
def _print_errors(errors: list[str]) -> None:
    print("✗ Commit message rejected:", file=sys.stderr)
    for err in errors:
        for line in err.splitlines():
            print(f"  → {line}", file=sys.stderr)
    print("  → Guide: docs/GIT.md", file=sys.stderr)


def _self_test() -> int:
    cases: list[tuple[str, bool]] = [
        ("feat(engine): scale workers with advisory leases\n", True),
        ("fix(sql): correct migration 028 index for Postgres 17\n", True),
        ("docs: document commit message practice\n", True),
        ("chore(ci)!: drop public Storybook hosting\n", True),
        ("Merge branch 'cursor/x' (#12)\n", True),
        ("Revert \"feat(backend): add lease\"\n", True),
        ("fixup! wip probe\n", True),
        ("Fixed the bug\n", False),
        ("feat(backend): add lease.\n", False),
        ("feat(backend): wip\n", False),
        ("feat(backend): Added lease helper\n", False),
        ("updates\n", False),
        ("feat(backend): add lease\nbody without blank\n", False),
        ("feat(backend): add lease\n\nExplain why the lease exists.\n", True),
        ("", False),
    ]
    failed = 0
    for msg, expect_ok in cases:
        errs = validate_commit_message(msg)
        ok = not errs
        if ok != expect_ok:
            failed += 1
            print(f"FAIL expect_ok={expect_ok} got_ok={ok}: {msg!r} → {errs}")
    if failed:
        print(f"✗ {failed} self-test case(s) failed", file=sys.stderr)
        return 1
    print(f"✓ commit-msg self-test OK ({len(cases)} cases)")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[1] == "--self-test":
        return _self_test()

    if len(argv) >= 2 and argv[1] != "-":
        text = Path(argv[1]).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    errors = validate_commit_message(text)
    if errors:
        _print_errors(errors)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
