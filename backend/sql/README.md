# FORJD Supabase SQL

Apply with `backend/scripts/apply_sql_migrations.py`. It discovers the
contiguous `003+` sequence, runs each file in its own transaction, fails fast,
and records/checks SHA-256 in `public.forjd_schema_migrations`. The verifier
requires ledger/checksum parity through every current file. Existing databases
that were maintained only through the SQL editor must run the script once; the
idempotent migrations are reapplied to backfill the ledger.

| File | Purpose |
|------|---------|
| `001_pulses.sql` | Historical — unused (legacy stack smoke table) |
| `002_anomaly_embeddings.sql` | Historical — unused (prefer tenant-scoped `/api/v1/ml`) |
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
| `020_headless_siem_soar.sql` | PII-minimized signals, whole-correlation receipts, immutable run plans, leased webhook retries, append-only audit enforcement, SIEM/SOAR scopes + RLS |
| `021_ingest_projection_reliability.sql` | Additive sealed-ingest identity, versioned non-blocking projection replay/DLQ state, and hash-only erase-retry tombstones |
| `022_report_documents.sql` | Tenant-scoped report documents (partner issue reports) + `reports:*` scopes + RLS |
| `023_durable_exports.sql` | Idempotent queued exports, worker leases, private object artifacts, and expiry |
| `024_durable_ingest_processing.sql` | Atomic sealed-acceptance processing receipts, immutable workflow snapshots, leased restart recovery, and status state |
| `025_siem_soar_replay_continuation.sql` | Immutable completed SIEM/correlation result snapshots and indexed SOAR continuation recovery |

## Secure path (`003`–`025`)

1. Enable extensions **vector** and **pgcrypto** (Dashboard → Database → Extensions).
2. Run `uv run python scripts/apply_sql_migrations.py` for `003` → `025` and
   confirm the migration ledger/checksums.
3. Realtime: `015`/`016` add `stream_results`, `telemetry_events`, `ml_scores`, `training_runs` when publication exists.
4. Set backend env: `SUPABASE_URL`, `SUPABASE_JWT_SECRET` (or rely on JWKS), `POSTGRES_DSN` (Supabase only — not Neon).
5. Add SaaS use cases as YAML under `backend/workflows/` (see that folder’s README).
6. After `017`–`024`, remint opaque `fjsvc_` tokens (`scripts/remint_service_account.sh`) so stored scopes include sessions/replay/status/analytics/exports/vulns/integrations, normalized SIEM/cases/playbooks, and report documents (plus `tenants:erase` when opted in).
7. Tenant erase: `POST /api/v1/tenants/{id}/erase` (human owner/admin or service with `tenants:erase`). A committed opaque-service retry uses only the hash/prefix tombstone in the surviving receipt and is valid on that exact same-tenant route only.
8. Post-check: `python backend/scripts/verify_supabase_post_migration.py` (or SQL in `scripts/verify_supabase_post_migration.sql`).
9. Neon consolidation (partner control plane): [`docs/NEON_TO_SUPABASE.md`](../../docs/NEON_TO_SUPABASE.md).
10. Final ops checklist: [`docs/PRODUCTION_CHECKLIST.md`](../../docs/PRODUCTION_CHECKLIST.md).

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

### Selectively disclosed SIEM lane

`security_signals` is not a plaintext copy of sealed evidence. It contains only
the strict, bounded, PII-minimized normalized fields a trusted partner elects
to disclose for search, correlation, case creation, and SOAR. Raw evidence
remains in `telemetry_events`; sql/020 enforces tenant idempotency, useful
indexes, constraints, and RLS. `playbook_runs` and
`playbook_action_results` persist truthful automation state, acknowledgements,
bounded retry schedules, and exclusive leases. Run action plans are immutable;
correlation receipts bind tenant/key/payload for whole-operation replay safety.
Sql/025 also snapshots completed public SIEM/correlation results so exact
replays never evaluate a newer rule or playbook definition, and indexes
nonterminal runs for continuation recovery after a successful action or ACK.
