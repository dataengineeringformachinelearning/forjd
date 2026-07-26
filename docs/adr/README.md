# Architecture Decision Records

Short records of **non-obvious** choices that agents and humans should not
re-litigate casually. Narrative architecture stays in [`ARCHITECTURE.md`](../../ARCHITECTURE.md)
and [`AGENTS.md`](../../AGENTS.md); ADRs capture *why* a pattern exists.

## Format

Each ADR is a Markdown file `NNNN-slug.md` with:

| Section | Purpose |
|---------|---------|
| Status | `Accepted` \| `Superseded by ADR-XXXX` \| `Deprecated` |
| Context | Forces / constraints |
| Decision | What we chose |
| Consequences | Follow-ons and what not to do |

## Index

| ADR | Title |
|-----|-------|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions |
| [0002](0002-ciphertext-only-partner-boundary.md) | Ciphertext-only lane + partner subprocessor tokens |
| [0003](0003-rust-streams-polars-batch.md) | Rust streams, Polars batch, Python soft fallback |
| [0004](0004-config-catalog-inventory-sot.md) | Config catalog as inventory SoT |
| [0005](0005-observability-correlation-first.md) | Correlation-first observability (no second metrics stack) |
| [0006](0006-landing-layers-suite-adapter.md) | Landing layers + forjd-ui suite adapter |
| [0007](0007-sole-rate-limiter-and-addons.md) | Sole rate limiter + FORJD_ADDONS flags |
| [0008](0008-optimistic-ui-with-rollback.md) | Optimistic UI with rollback (`runOptimistic`) |
| [0009](0009-graceful-offline-landing.md) | Graceful offline handling for the landing |
| [0010](0010-normalize-flat-reactive-state.md) | Normalize data structures / flat reactive state |
| [0011](0011-consistent-fetch-states.md) | Consistent data-fetching states (loading / error / success) |
| [0012](0012-swr-cache-invalidation.md) | Cache invalidation + background revalidation (SWR) |
| [0013](0013-client-side-attack-hardening.md) | Client-side attack hardening (XSS, CSRF, open redirects) |
| [0014](0014-sanitize-ugc-and-third-party.md) | Sanitize UGC and third-party data |
| [0015](0015-rate-limit-validation-output-encoding.md) | Rate limiting, input validation, output encoding |
| [0016](0016-secure-defaults-cookies-headers-api.md) | Secure defaults for cookies, headers, API communication |
| [0017](0017-secrets-and-sensitive-data.md) | Secrets and sensitive data (client + server) |
| [0018](0018-defensive-outbound-http.md) | Defensive outbound HTTP and unexpected data shapes |
| [0019](0019-command-history-undo-redo.md) | Command history for undo/redo (reversible client actions) |
| [0020](0020-priority-toast-notifications.md) | Priority toast notifications (non-intrusive, importance-ordered) |
| [0021](0021-bulk-actions-multi-select.md) | Bulk actions and multi-select on lists/tables |
| [0022](0022-smart-defaults-progressive-disclosure.md) | Smart defaults + progressive disclosure for advanced UI |
| [0023](0023-keyboard-shortcuts.md) | Keyboard shortcuts registry + `?` help |
| [0024](0024-preferences-persist-sync.md) | Preferences persist + cross-tab sync |
| [0025](0025-onboarding-empty-guidance.md) | Onboarding and empty-state guidance |
| [0026](0026-suite-data-pack-export-import.md) | Suite data pack export / import |
| [0027](0027-client-activity-log.md) | Client activity log for important soft-chrome actions |
| [0028](0028-yaml-workflows-validate-cli.md) | YAML workflows as SoT + validate CLI (no partner write API) |

## When to add one

- A choice would surprise a competent new contributor
- Two reasonable alternatives were rejected for security/stability reasons
- A “do not invent X” invariant is easy to violate under pressure

Skip ADRs for routine refactors, dependency bumps, or choices already fully
specified by an accepted ADR.

## Adding

1. Copy the newest number + 1 → `NNNN-short-slug.md`
2. Link it from this index
3. Point the relevant code module docstring at `docs/adr/NNNN-…`
4. Optionally append one line to `LOG.MD`
