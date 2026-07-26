# ADR-0025: Onboarding and empty-state guidance

## Status

Accepted — 2026-07-26

## Context

First-time users hit empty lists and a one-shot DEML wizard with ad-hoc
`deml_onboarding_*` keys. FORJD’s landing sequence was static marketing copy
with no progress tracking. Empty states used mixed hand-rolled markup. We need
one suite journey store and checklist chrome without inventing a second empty
system or a fake FORJD product console.

## Decision

1. Dual-adapter **`createOnboardingStore`** persists journey state in
   **`suite-onboarding-v1`** (JSON: `dismissed`, `completed`, `completedSteps`,
   `activeFlow`, `updatedAt`). Separate from `suite-preferences-v1` (ADR-0024).
2. **Migrate** `deml_onboarding_skipped` / `deml_onboarding_complete` once, then
   clear legacy keys.
3. **Sync**: `storage` + `suite-onboarding-change` CustomEvent (same pattern as
   preferences).
4. **UI**: `forjd-onboarding-checklist` / `viking-onboarding-checklist` for
   interactive steps; empty surfaces keep **`forjd-empty` /
   `viking-empty-state`** with **`SUITE_EMPTY_GUIDANCE_EYEBROW`** (`Getting
   started`) and projected CTAs.
5. **Product flows**: DEML status wizard remains the heavy path
   (`activeFlow: deml-status`); FORJD landing Bind→Seal→Project→Operate is an
   optional partner checklist (`forjd-partner`). No fake console on forjd.co.
6. **Never** store `fjsvc_`, JWTs, API keys, or ciphertext in the onboarding blob.

## Consequences

- `OnboardingService` (DEML) reads/writes the suite store
- Settings empty rows use `viking-empty-state` + guidance eyebrow
- Dashboard shows the checklist until dismissed/complete; wizard auto-open stays
- Docs: [`docs/ONBOARDING.md`](../ONBOARDING.md)
