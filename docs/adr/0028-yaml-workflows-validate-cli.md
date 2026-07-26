# ADR-0028: YAML workflows as SoT + validate CLI (no partner write API)

## Status

Accepted — 2026-07-26

## Context

Partners need new sealed-stream use cases without forking ingest or crypto.
A product console or `POST /workflows` would expand the attack surface, invite
cross-tenant misconfiguration, and contradict the “landing is docs only”
boundary. Soft-skipping unknown detector steps at runtime is good for
extensibility but hides typos until production traffic arrives.

## Decision

1. **YAML/JSON under `backend/workflows/` remains the source of truth.** There is
   no partner write API and no browser persistence of workflow definitions on
   FORJD. DEML Pipeline Studio may *compose and export* YAML only.
2. **Local/CI validation is fail-closed:** `npm run validate:workflows` (and
   `scripts/validate_workflows.py`) check Pydantic schema, registered
   processors/detectors, E2EE-only encryption, and duplicate ids. CI and
   `npm run quality` run this gate; pre-commit runs it when workflow paths change.
3. **Runtime soft-skip stays the default** for unknown steps so unregistered
   custom detectors do not hard-crash ingest. Optional `WORKFLOWS_STRICT=1`
   raises at registry load for deployments that want fail-closed parity with CI.
4. **Templates live under `examples/`** (not loaded at runtime). Extension map:
   [`docs/EXTENDING.md`](../EXTENDING.md).

## Consequences

- Partners/operators: edit YAML → `validate:workflows` → deploy/reload API
- Custom detectors need `REGISTRY` (+ Rust parity for hot path) — document in
  EXTENDING; unknown steps fail CI even if runtime soft-skips
- Do not invent a FORJD workflow write API or product console to “fix” DX
- Related: ADR-0002 (ciphertext-only), ADR-0004 (config catalog), ADR-0007 (addons)
