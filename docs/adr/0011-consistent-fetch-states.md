# ADR-0011: Consistent data-fetching states

## Status

Accepted — 2026-07-26

## Context

Client requests need the same lifecycle everywhere: **idle → loading → success|error**.
Ad-hoc booleans (`isLoading` + separate `error` + implied success) drift; nested
`{ status, data, error }` VMs fight ADR-0010. FORJD’s landing only probes
`/ready` today, but table/virtual-list already expose `loading` / `error` slots —
the domain layer should speak one language.

## Decision

1. **Canonical phases:** `idle` | `loading` | `success` | `error` via
   `createFetchHandle` in `frontend/src/app/core/fetch/`.
2. **Flat signals:** `phase`, `data`, `error` plus derived `isLoading` /
   `isSuccess` / `isError` / `isIdle` — never one nested reactive object.
3. **Two runners:**
   - `run` — throwing fetchers (map unknown → error string)
   - `runSettled` — soft domain outcomes (`FetchSettled`) for probes like `/ready`
4. **Presentation contract:** templates bind suite slots —
   error → `forjd-error-state` / callout; loading → `forjd-loading` / skeleton /
   badge; success → content. Data components already take `loading` + `error` inputs.
5. **`/ready` rules unchanged:** no optimistic-ok (ADR-0008); `offline` ≠
   `unreachable` (ADR-0009); soft failures are `error` phase with typed
   `ReadyFetchError`, not thrown exceptions.
6. **forjd-ui does not fetch** — handles live in app `core/`; primitives only
   render the three states they are given.

## Consequences

- New client reads should use `createFetchHandle` instead of inventing booleans
- Abort/supersede is built in; DestroyRef should `abort()`
- Do not introduce NgRx/TanStack Query for the landing-only surface
- Cache invalidation / SWR lives beside this handle — see ADR-0012
