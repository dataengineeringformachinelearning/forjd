# Production checklist — FORJD

Operator checklist for the FORJD platform. Partner BFF / UI steps live in the
partner repo. Deploy commands: [`PRODUCTION_DEPLOY.md`](./PRODUCTION_DEPLOY.md).

| Layer | Owner | Host |
|-------|--------|------|
| Sealed streaming, projections, ML, exports, vulns, status | FORJD | Fly `forjd-backend` + `forjd-engine` |
| Cache (data plane) | FORJD | Fly Dragonfly (`forjd-dragonfly`) |
| Data-plane Postgres | FORJD | Supabase `public` (+ RLS / Realtime) |
| Partner user plane | Partner | Partner hosts |

---

## A. Schema + service principals

| Step | Action |
|------|--------|
| A1 | Run `apply_sql_migrations.py` for `003` → `028`; confirm `forjd_schema_migrations` checksum parity (run once on SQL-editor-managed DBs to backfill ledger) |
| A2 | Mint generic `fjsvc_` credentials with `scripts/remint_service_account.sh`; confirm `027` upgraded every active DEML credential with `ml:write` in place |
| A3 | Run `verify_supabase_post_migration.py`; require zero partner duplicates/aliases, credential/tenant mismatches, status/probe child mismatches, and active DEML scope gaps, plus validated `027`/`028` constraints |
| A4 | Confirm `/ready` reports `schema_rls=true` |
| A5 | Set `OUTBOUND_HOST_ALLOWLIST` to exact custom TAXII/webhook hosts (or deliberate `*.` suffixes); empty fails closed in production |
| A6 | Put webhook HMAC keys in the deployment secret manager as `WEBHOOK_SIGNING_SECRETS_JSON`; playbooks store only opaque `secret_ref` keys |
| A7 | Configure a private S3-compatible export bucket, least-privilege list/get/put/delete credentials, encryption/retention policy, and `OBJECT_STORAGE_*`; production `/ready` must report `object_storage=true` |

```bash
./scripts/remint_service_account.sh partner-production
# Dedicated account-deletion credential only; erase is excluded by default:
FORJD_INCLUDE_ERASE=1 ./scripts/remint_service_account.sh partner-deletion
```

## B. Fly deploy

| Step | Action |
|------|--------|
| B1 | Freeze DEML provisioning and ML writes before the `027` scope expansion |
| B2 | Confirm secrets on `forjd-backend` (`POSTGRES_DSN`, `REDIS_URL`, `SUPABASE_*`, `ENGINE_*`, `OBJECT_STORAGE_*`, `ENVIRONMENT=prod`) |
| B3 | Deploy the hardened API while schema `026` is still live; confirm `/health` |
| B4 | Apply `027`/`028` and require `verify_supabase_post_migration.py` to pass |
| B5 | Deploy/restart the ML worker + engine (`FORJD_ROLE=all` + internode keys); confirm `https://backend.forjd.co/ready` |
| B6 | Run the DEML tenant-bound ML smoke, then unfreeze traffic |

## C. Partner smoke

1. Mint service account → canonical sealed `POST /api/v1/ingest/events:batch` → projections list.
   Confirm `/api/v1/capabilities` advertises 25 events / 8 MiB, and both an
   oversized `Content-Length` request and an oversized chunked request return `413`.
   Kill the API after acceptance but before synchronous processing; after
   restart verify the leased ingest worker completes the returned receipt and
   `GET /api/v1/ingest/processing/{batch_id}` reports `completed`.
2. Analytics overview → status page CRUD → exports/vulns as scoped.
   For DEML, fit and score one tenant-bound ML model and confirm the provisioned
   service account has `ml:write` without wildcard scope.
   Race two ordinary provision requests and confirm one tenant/account is
   created; serialize explicit remints per external identity.
3. Normalized signal exact retry → one signal, one correlated case, idempotent playbook runs.
4. Case/vulnerability/playbook PATCH; manual execute; idempotent control-plane ACK; leased webhook retry and explicit operator retry.
5. Edit a playbook while a run is paused and verify its immutable action plan is unchanged; verify correlation and legacy alert exact replay/conflict behavior.
6. Wrong-tenant, missing-scope, private-egress, redirect, and oversized TAXII requests fail closed; audit write failure also fails privileged SIEM/SOAR requests and atomically rolls back sealed-ingest events plus processing receipts.
7. Staging tenant erase: `POST /api/v1/tenants/{id}/erase`; repeat it with the
   now-deleted opaque credential and verify the completed receipt is returned,
   verify multi-tenant `ingest_processing_batches` metadata containing that
   tenant was removed, then verify that credential still gets `401` on another
   route and tenant.
8. Force one projector page to fail; verify its events enter the versioned DLQ,
   the next page proceeds, and retry either succeeds at the stored version or
   fails closed on deliberate workflow-version drift.
9. Retry an exact accepted batch whose processing receipt is pending/failed;
   verify it wakes the original stored workflow snapshot and does not create a
   differently grouped processing job.
10. Create the same export twice with one idempotency key; verify one leased
    job, checksum/byte count, short-lived signed download, expiry cleanup, and
    artifact deletion during tenant erase.

## D. Separation invariants

| Concern | Partner | FORJD |
|---------|---------|-------|
| End-user auth | Partner IdP (e.g. Firebase) | Supabase Auth (platform) / `fjsvc_` (partners) |
| Browser API | Partner BFF only | Never called with partner end-user tokens |
| Sealed evidence | BFF → FORJD `/ingest/events:batch` | Ciphertext storage + metadata projections |
| Normalized SIEM / SOAR | BFF → FORJD `/siem/signals` | PII-minimized signals, cases, durable playbook runs |
| Cache | Optional / none | Fly Dragonfly |
| Tenant erase | Calls FORJD erase then local teardown | `POST /api/v1/tenants/{id}/erase` |
| CSRF | Partner CSRF + header auth at BFF | Header credentials only (no CSRF tokens) |
| XSS headers | Partner CSP | API CSP `default-src 'none'` + SPA CSP on Vercel |

## D2. Security headers smoke

| Step | Action |
|------|--------|
| D2.1 | `curl -sI https://backend.forjd.co/health` includes `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` |
| D2.2 | Landing (`https://forjd.co`) responses include CSP and HSTS from `frontend/vercel.json` |
| D2.3 | Unauthenticated mutating `POST /api/v1/*` returns `401` (no cookie-only success path) |

## E. Rollback

| Issue | Action |
|-------|--------|
| Bad API/engine deploy | Freeze DEML ML writes before any API rollback; never run pre-hardening ML behavior with `027` grants; engine → `FORJD_ROLE=engine` |
| Ingest errors | `/ready`, Dragonfly, crypto sessions, workflows |
| Scope 403s | Run the verifier; `027` updates active DEML scopes in place, while generic credentials may require an intentional remint |
