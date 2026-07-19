# FORJD Supabase SQL

Apply in order in the Supabase SQL editor (or `psql`).

| File | Purpose |
|------|---------|
| `001_pulses.sql` | Stack pulse PoC |
| `002_anomaly_embeddings.sql` | Legacy ML PoC embeddings |
| `003_secure_tenancy.sql` | **Production path** — tenants, RLS, E2EE telemetry, vector embeddings |
| `004_crypto_sessions.sql` | X25519 public-key session directory (private keys never stored) |
| `005_stream_results.sql` | Pathway/Prefect outputs (metadata scores; RLS) |
| `006_universal_stream.sql` | `event_type` / `workflow_id`, `use_cases`, `sealed_events` view |
| `007_projections.sql` | Durable projections, checkpoints, DLQ |
| `008_status_pages.sql` | Status pages / services / incidents (public when published) |
| `009_daemon_data_plane.sql` | Rust daemon outbox, scheduler, API keys, normalizer, probes |
| `010_audit_and_rate_limits.sql` | Metadata-only `audit_events` + `daemon_api_keys.rate_limit_rpm` |
| `011_domain_security.sql` | Domain security — threat intel, SOC cases, playbooks, exports, ML runs |
| `012_domain_scanners.sql` | Lighthouse, OSINT endpoints, validated sites, honeypots, report archives |
| `013_e2ee_hardening.sql` | Nonce uniqueness `(tenant_id,key_id,nonce)` + `crypto_sessions.revoked_at` |
| `014_service_accounts.sql` | Tenant-scoped M2M / subprocessor principals (`fjsvc_` + Auth binding) |
| `015_realtime_and_consumer.sql` | Realtime publication, `projection_feed` view, cursor indexes, sessions scopes |
| `016_ml_supabase.sql` | ML `training_runs` family columns, `ml_scores` + RLS, Realtime for ML |
| `017_service_principal_cutover.sql` | Drop `crypto_sessions.user_id` → `auth.users` FK; expand default service scopes |
| `018_partner_domain_scopes.sql` | Default scopes for exports/vulns/integrations (remint required) |
| `019_least_privilege_erase_scope.sql` | Drop `tenants:erase` from DEFAULT scopes (opt-in at mint/remint) |

## Secure path (`003`–`018`)

1. Enable extensions **vector** and **pgcrypto** (Dashboard → Database → Extensions).
2. Run `003` → `018` in order.
3. Realtime: `015`/`016` add `stream_results`, `telemetry_events`, `ml_scores`, `training_runs` when publication exists.
4. Set backend env: `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (or rely on JWKS), `POSTGRES_DSN` (Supabase only — not Neon).
5. Add SaaS use cases as YAML under `backend/workflows/` (see that folder’s README).
6. After `017`/`018`, remint opaque `fjsvc_` tokens (`scripts/remint_service_account.sh`) so stored scopes include sessions/replay/status/analytics/exports/vulns/integrations/`tenants:erase`.
7. Tenant erase: `POST /api/v1/tenants/{id}/erase` (human owner/admin or service with `tenants:erase`).
8. Post-check: `python backend/scripts/verify_supabase_post_migration.py` (or SQL in `scripts/verify_supabase_post_migration.sql`).
9. Neon consolidation (partner control plane): [`docs/NEON_TO_SUPABASE.md`](../../docs/NEON_TO_SUPABASE.md).
10. Final ops checklist: [`docs/PRODUCTION_CUTOVER_CHECKLIST.md`](../../docs/PRODUCTION_CUTOVER_CHECKLIST.md).

### Roles

| Client | How |
|--------|-----|
| Browser / Realtime | Supabase anon key + user JWT → RLS via `auth.uid()` |
| FastAPI (enterprise user) | Verify Supabase JWT → service-role DSN → `tenant_members` |
| FastAPI (subprocessor) | Opaque `fjsvc_…` or service-shaped JWT → `service_accounts` tenant + scopes |
| Auth details | [`backend/docs/AUTH.md`](../docs/AUTH.md) |

### E2EE (Signal-inspired)

| Piece | Role |
|-------|------|
| X25519 ECDH + HKDF | Client derives per-session AES-256 keys |
| AES-256-GCM | Seals each event; AAD binds `tenant_id\|client_event_id` |
| Double Ratchet | Client-owned forward secrecy; `ratchet_header` opaque to server |
| `telemetry_events.ciphertext` | Encrypted payload only (server-blind) |
| `crypto_sessions` | Public keys for peer discovery — never private keys |
| Pathway | Rolls up metadata + size anomalies, never decrypts |
| `stream_results` | Consumer-facing scores/rollups (no ciphertext) |
| `projection_feed` | View over `stream_results` for Realtime / polling clients |
| `use_cases` | Optional DB catalog of workflows |
| `sealed_events` | View alias over `telemetry_events` |

Plaintext never crosses the API on the E2EE path. Downstream SaaS consumers
(analytics, threat, telemetry, …) read `stream_results` / `projection_feed`
(and optionally sealed events for client decrypt) under RLS.
