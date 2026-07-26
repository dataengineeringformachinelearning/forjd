# ADR-0001: Record architecture decisions

## Status

Accepted — 2026-07-26

## Context

FORJD’s durable narrative lives in `ARCHITECTURE.md` / `AGENTS.md`, but those
docs mix product briefing with scattered “why” notes. Agents repeatedly
re-propose second stacks (extra rate limiters, APM, design systems, DEML-local
data planes) that were already rejected.

## Decision

Keep **ADRs** under `docs/adr/` for non-obvious, stable choices. Keep product
and layer maps in `ARCHITECTURE.md` / `AGENTS.md`. Prefer a short ADR plus a
one-line code pointer over long comments that narrate syntax.

## Consequences

- New non-obvious patterns get an ADR before they spread
- Code comments cite `docs/adr/NNNN-…` instead of restating the essay
- Superseding an ADR requires a new ADR that names the old one
