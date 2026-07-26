# ADR-0022: Smart defaults and progressive disclosure

## Status

Accepted — 2026-07-26

## Context

Dense settings and ops forms (telemetry IDs, provider integrations, export
options, API key minting) overwhelm first-time users when every control is
visible at once. We need **smart defaults** for common choices and
**progressive disclosure** for advanced sections — without inventing a second
preference store or a global “expert mode” flag.

## Decision

1. Dual-adapter **`createDisclosureStore`** (forjd-ui + viking-ui):
   - Sections resolve `remembered → fallback → defaults → false` (collapsed)
   - Persist expand state in `suite-disclosure-v1` (never secrets)
2. **`forjd-disclosure` / `viking-disclosure`** — non-modal advanced panel with
   badge, heading, description, and `sectionId`; chrome via `.suite-disclosure`
3. Product composition sets **smart defaults**:
   - Advanced site options (telemetry, embed, integrations) → `defaultOpen=false`
   - Generate API key / export form → open when empty, collapsed once rows exist
   - Form fields keep sensible presets (e.g. export `analytics` / `csv` / `7` days)
4. Do not invent a parallel accordion-only preference API for this; reuse the
   disclosure store. Full `viking-accordion` remains for FAQ-style multi-panels.

## Consequences

- New users see essentials first; power users expand once and the choice sticks
- Hosts must use stable `sectionId` strings (`deml.settings.telemetry`, …)
- Reset via `createDisclosureStore().reset()` restores smart defaults
