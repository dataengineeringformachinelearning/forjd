# Production deploy — FORJD (Fly + Vercel)

Final operator runbook for the FORJD platform. Partner BFF/UI steps live in each
partner's own deploy runbook.

**Previously recorded live baseline (2026-07-18; rerun after this release):**

| Check | Result |
|-------|--------|
| `https://backend.forjd.co/health` | `healthy` / production |
| `https://backend.forjd.co/ready` | postgres + redis + `schema_rls=true` + engine ok |
| Engine | `forjd_role=All`, data_plane enabled, `/ready` 200 |
| Fly apps | `forjd-backend`, `forjd-engine`, `forjd-dragonfly` started (iad) |

---

## 1. Expansion-safe release order

Migration `027` expands active DEML credentials with `ml:write`. Freeze DEML
provisioning and ML writes first, then deploy the hardened API image before
granting that scope. The new API remains compatible with schema `026`; do not
unfreeze traffic until the migrations and verifier both pass.

1. Freeze DEML provisioning and ML fit/score requests.
2. Deploy the new `forjd-backend` image and confirm `/health`.
3. Apply `027` and `028`, then require the post-migration verifier to pass.
4. Deploy/restart the ML worker and engine, confirm `/ready`, then run the DEML
   tenant-bound ML smoke before unfreezing traffic.

If organizational policy requires schema-first deployment, keep DEML
provisioning and ML writes disabled until the hardened API is live and the
verifier passes.

### Supabase schema

```bash
cd backend
# Requires POSTGRES_DSN / DATABASE_URL in env (never commit)
uv run python scripts/apply_sql_migrations.py   # 003 → 028

POSTGRES_DSN='…' uv run python scripts/verify_supabase_post_migration.py
```

The migration runner applies each file transactionally and records its SHA-256
in `forjd_schema_migrations`; the verifier requires ledger/checksum parity.
Existing databases previously managed only through the SQL editor must run the
script once to idempotently backfill that ledger.

After `017`–`024`, remint partner tokens so stored SIEM/SOAR,
report-document, export, and ingest-processing scope arrays are current:

```bash
export FORJD_API_URL=https://backend.forjd.co
export FORJD_HUMAN_JWT='…'   # human owner/admin
export FORJD_TENANT_ID='…'
./scripts/remint_service_account.sh partner-production
# Dedicated account-deletion credential only; erase is excluded by default:
FORJD_INCLUDE_ERASE=1 ./scripts/remint_service_account.sh partner-deletion
```

Migration `027` fails closed if a provision ledger credential belongs to a
different tenant or multiple provision identities alias one tenant/credential,
then enforces one-to-one mapping and the composite credential/tenant FK. It
upgrades every active DEML credential with tenant-bound `ml:write` in place; opaque
authentication reads current database scopes, so no token rotation is required.
New DEML provisions receive the same explicit profile, while generic
service-account defaults remain unchanged.
Migration `028` fails closed on mismatched status children, then validates
composite page/tenant foreign keys for services and incidents and a
service/tenant foreign key for probe observations. It also indexes each
service's newest probe observation for bounded readiness checks; schedule the
migration during a low-write window if that history table is already large.

---

## 2. Fly.io — API (`forjd-backend`)

From **repo root** (Dockerfile builds Rust wheel):

```bash
# From repo root — config is fly.api.toml (Dockerfile: backend/Dockerfile)
fly deploy -a forjd-backend -c fly.api.toml
# Secrets (once): POSTGRES_DSN, REDIS_URL, SUPABASE_*, ENGINE_URL,
# ENGINE_API_TOKEN, OBJECT_STORAGE_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET,
# ENVIRONMENT=production, CORS_ORIGINS including https://forjd.co,
# OUTBOUND_HOST_ALLOWLIST=taxii.vendor.com,*.hooks.partner.example
# WEBHOOK_SIGNING_SECRETS_JSON={"primary-hook":"secret-manager-value"}
```

```bash
curl -fsS https://backend.forjd.co/health
curl -fsS https://backend.forjd.co/ready
# Security headers (XSS hardening; CSRF = Bearer / X-API-Key, not tokens)
curl -sI https://backend.forjd.co/health | grep -Ei 'content-security-policy|x-content-type-options|x-frame-options'
fly checks list -a forjd-backend
```

The private S3-compatible bucket credentials need only list/get/put/delete on
the export bucket. Enable provider-side encryption and a lifecycle expiration
at least as strict as `EXPORT_TTL_SECONDS`. Production readiness performs a
bounded bucket probe and also reports the ingest, SOAR, and export workers.
Keep `EXPORT_MAX_SOURCE_BYTES` within measured worker memory; source reads are
repeatable-read, paged, and fail before rendering when that budget is exceeded.

---

## 3. Fly.io — Engine (`forjd-engine`)

```bash
cd engine
fly deploy -a forjd-engine
# FORJD_ROLE=all needs DSNs + internode keys:
#   ../scripts/sync_engine_dataplane_secrets.sh
curl -fsS https://forjd-engine.fly.dev/ready
```

Private URL for API: `http://forjd-engine.internal:8080`.

---

## 4. Vercel — FORJD web (`forjd.co`)

```bash
cd frontend
npx vercel link --project forjd --yes   # adjust project name if different
# apiBaseUrl = https://backend.forjd.co (see frontend env / vercel.json)
npx vercel deploy --prod --yes
```

Optional Storybook: `ui.forjd.co` (separate Vercel project).

DNS: `backend.forjd.co` → Fly `forjd-backend` (`fly certs add backend.forjd.co`).

---

## 5. Rollback

| Issue | Action |
|-------|--------|
| Bad API deploy | `fly releases -a forjd-backend` → prior image (SQL forward-only) |
| Bad engine deploy | Prior engine release; or `FORJD_ROLE=engine` (process-only) |
| Ingest errors | Check `/ready`, Dragonfly, crypto sessions, workflow YAML |
| Scope 403s | Run the post-migration verifier first; `027` updates active DEML scopes in place, while generic credentials may require intentional remint |
| Partner freeze | Partner sets write/read `off`; ciphertext remains in Supabase |

Do not soft-migrate schema in prod. Do not accept `service_role` JWTs.
SQL migrations are forward-only. After `027` permits the same `external_ref`
in different partner namespaces, never roll the API back to a version that
queries `external_ref` without `partner`; freeze provisioning and prove global
reference uniqueness first if an emergency code rollback crosses that boundary.
Do not roll the API back to pre-hardening ML behavior while any DEML credential
retains the `ml:write` grant introduced by `027`; freeze ML writes instead.
The migration runner and verifier reject ledger versions unknown to the
checked-out release, so use a code revision that knows the live schema.
Do not blanket-remove `ml:write` to reverse `027`, because preexisting explicit
grants are indistinguishable from the in-place upgrade.

---

## 6. Sealed-path smoke (service token)

1. `POST /api/v1/sessions` — register X25519 pubs (`sessions:write`).
2. `POST /api/v1/ingest/events:batch` — canonical DEML/partner AES-256-GCM batch contract.
   Verify `/api/v1/capabilities` reports 25 events and 8 MiB, then confirm
   oversized declared and chunked bodies return `413` before application work.
   Confirm the response includes durable processing receipt IDs, then restart
   between acceptance and processing and poll `/api/v1/ingest/processing/{id}`
   until the supervised leased worker reports `completed`. Confirm the same
   acceptance transaction also wrote its tenant-scoped `ingest.batch` audit
   event; a forced audit-insert failure must leave neither event nor receipt.
3. `GET /api/v1/projections` — scores/metadata (no ciphertext).
4. Status CRUD + analytics overview as scoped.
5. `POST /api/v1/siem/signals` twice with the same `client_signal_id`; verify the second receipt has `duplicate=true` and no duplicate case/run.
6. Case PATCH; playbook create/PATCH/execute; verify partner-owned actions remain `awaiting_ack` until the action ACK endpoint is called. Force a webhook `503`/`429`, verify leased bounded retries retain one `Idempotency-Key`, and exercise the explicit retry endpoint for a permanent `4xx`.
7. Verify wrong-tenant tokens and missing SIEM/SOAR scopes return `403`.
8. Verify production custom TAXII/webhooks fail closed unless their hostname is in `OUTBOUND_HOST_ALLOWLIST`.
   Confirm playbook edits do not change an already-created run's frozen action plan,
   conflicting ACK decisions return `409`, and audit rows reject update/delete.
9. Staging: `POST /api/v1/tenants/{id}/erase` with `tenants:erase`; simulate a
   lost response by repeating with the deleted opaque token, verify the same
   completed receipt, confirm processing batches containing that tenant are
   erased, and confirm that token gets `401` everywhere else.
10. Inject a projector failure; verify atomic handoff to the versioned DLQ,
    advancement of the live cursor, processing of later events, and safe exact
    replay (or a fail-closed response when the workflow version has changed).
11. Retry an exact accepted batch with a pending/failed processing receipt and
    confirm FORJD wakes the original ordered workflow snapshot rather than
    creating a new interpretation of the event group.
12. Create an idempotent export, poll it to completion, verify its checksum and
    short-lived signed download, then verify expiry and tenant erasure remove
    the private object. Configure a bucket lifecycle as defense in depth.

The Rust `/api/v1/ingest` compatibility shape is retired and returns `410 Gone`
after authentication and validation. It never claims acceptance. All DEML,
partner, and daemon clients must use FastAPI `/api/v1/ingest/events:batch`.

---

## Production readiness

| Surface | Ready? |
|---------|--------|
| API + RLS | **Yes** |
| Engine data plane (`All`) | **Yes** |
| Dragonfly | **Yes** |
| Universal (no partner hardcoding) | **Yes** |
| sql/020 normalized SIEM/SOAR + remint | **Deploy required** (re-run remint after any scope-default change) |
| sql/021 ingest/projection reliability | **Deploy required** |
| sql/022 report documents + remint | **Deploy required** |
| sql/023 durable export jobs | **Deploy required** |
| sql/024 durable ingest processing recovery | **Deploy required** |
| sql/025 replay-safe SIEM/SOAR receipts + continuation recovery | **Deploy required** |
| sql/026 partner provision ledger | **Deploy required** |
| sql/027 partner isolation + DEML ML scope | **Deploy required** |
| sql/028 status child tenant integrity | **Deploy required** |

**Verdict:** the implementation is ready for the staging launch gate. Do not
declare a production cutover complete until `020`–`028` are applied, object
storage and worker checks are green, partner tokens are reminted, and the smoke
suite above passes against live Supabase, Dragonfly, engine, and object storage.
