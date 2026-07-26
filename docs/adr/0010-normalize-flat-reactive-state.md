# ADR-0010: Normalize data structures / flat reactive state

## Status

Accepted — 2026-07-26

## Context

Deeply nested reactive graphs (`signal({ a: { b: … } })`, view-models that
re-wrap every list item as `{ item, index }`, multi-key caches of nested
entries) make Angular Signals hard to reason about: coarse invalidation,
awkward templates, and accidental shared mutation. FORJD’s landing is small;
we still want patterns that scale to forjd-ui / Viking virtual lists without
entity-store ceremony.

## Decision

1. **Primitives in reactive state.** Prefer a scalar `signal` / enum status over
   a nested “VM object” that templates destructure. Derive flat `computed`
   fields (tone, heading, flags) for bindings.
2. **Flat caches.** Domain caches hold scalars (e.g. ready status + timestamp),
   not `{ data, fetchedAt }` entry objects unless the entry shape is unavoidable.
3. **Index lists for windows.** Virtual list/table windows expose
   `number[]` via `indicesForWindow(start, end)` and look up `items()[index]` in
   the template — never materialize `{ item, index }[]` as reactive state.
4. **Static content stays flat.** Landing metrics use `[label, value]` tuples;
   no nested reactive wrappers around copy.
5. **No premature entity store.** Do not invent `ids` / `byId` normalization for
   toast queues or landing copy until a real shared mutable collection needs it.

## Consequences

- Templates bind flat computeds; avoid `readyDegraded()?.tone` chains
- Suite adapters (forjd-ui + viking-ui) share the same window-index pattern
- Reject nested SWR maps and signal-of-object VMs on new landing/core code
