# ADR-0002: Ciphertext-only lane + partner subprocessor tokens

## Status

Accepted — 2026-07-26 (codifies long-standing invariants)

## Context

Partners (e.g. DEML) already authenticate end users (Firebase, etc.). FORJD must
process telemetry without becoming a second IdP or a plaintext SIEM dump. Storing
or logging envelope contents would break the E2EE promise and expand blast radius.

## Decision

1. **Sealed evidence lane** stores and routes **ciphertext only**. Processors
   (Rust hot path and Python soft fallback) never receive plaintext event bodies.
2. Partners call FORJD with a **tenant-bound** `fjsvc_` service token (or a
   Supabase user JWT for human operators). **Never** accept partner end-user
   tokens at the FORJD edge.
3. A separate **normalized signal lane** (`security_signals`) may hold
   PII-minimized, selectively disclosed fields for SIEM/SOAR — still never raw
   ciphertext or credentials.

## Consequences

- Logs, Rollbar/Sentry, and audit tables must scrub tokens/ciphertext
  (see ADR-0005)
- Partner BFFs map `account → forjd_tenant_id → secret_ref`; body/query tenant
  IDs must match or fail closed
- Details: `backend/docs/AUTH.md`, `ARCHITECTURE.md` (E2EE invariants)
