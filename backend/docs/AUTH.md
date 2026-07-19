# FORJD Authentication & Subprocessor Model

FORJD is a **universal secure streaming backend**. It serves:

1. **Enterprise / direct users** — humans on Supabase Auth (FORJD console / API).
2. **Trusted subprocessors** — machine callers (partner SaaS backends) that keep
   their **own** end-user identity and call FORJD with a **tenant-scoped
   service token**.

FORJD never accepts a partner's end-user tokens.

## Principal kinds

| Kind | Credential | Tenant binding |
|------|------------|----------------|
| `user` | Supabase Auth access JWT (`role=authenticated`) | Via `tenant_members` (multi-tenant) |
| `service` | Opaque `fjsvc_<prefix>_<secret>` **or** Supabase JWT with `app_metadata.forjd.principal_type=service` | Hard-bound to one `service_accounts.tenant_id` |

Resolved in `app.core.auth.AuthUser` (`kind`, `scopes`, `subprocessor`, `actor_id`).

**Rejected:** Supabase `service_role` JWTs on application routes (too privileged).

## Subprocessor flow

```
Partner end-user ──(partner auth)──► Partner SaaS backend
                                          │
                                          │ Authorization: Bearer fjsvc_…
                                          │ (tenant-scoped service account)
                                          ▼
                                       FORJD API
                          sessions → ingest → projections
                                          │
                                          ▼
                          telemetry_events (ciphertext)
                          stream_results / projection_feed
```

1. Enterprise admin creates a FORJD tenant and membership (human JWT).
2. Admin mints a service account: `POST /api/v1/service-accounts` with an
   optional `subprocessor` label (token returned **once**).
3. The partner stores the token as a secret; every call includes
   `Authorization: Bearer fjsvc_…` and the same `tenant_id` in the body/query.
4. FORJD enforces: token → single tenant + scopes (`ingest:write`, …).
5. Payloads remain E2EE: the partner (or its clients) seal with AES-256-GCM;
   FORJD stores ciphertext only. Register `crypto_sessions` before ingest when
   `REQUIRE_CRYPTO_SESSION=true` (default service scopes include `sessions:write`).

### Concrete HTTP sequence

```http
# 1) Human (Supabase JWT) mints a subprocessor token once
POST /api/v1/service-accounts
Authorization: Bearer <supabase_user_jwt>
{"tenant_id":"<uuid>","name":"production ingest","subprocessor":"partner-app"}

# 2) Partner registers an X25519 public session (service token)
POST /api/v1/sessions
Authorization: Bearer fjsvc_…
{"tenant_id":"<uuid>","session_id":"device-1","identity_public_key":"<b64>"}

# 3) Partner ingests a sealed envelope (ciphertext only)
POST /api/v1/ingest
Authorization: Bearer fjsvc_…
{"tenant_id":"<uuid>","client_event_id":"evt-1","content_type":"application/forjd-event+v1",
 "encryption":{"mode":"e2ee","algo":"aes-256-gcm"},
 "envelope":{"algo":"aes-256-gcm","key_id":"device-1","nonce":"<b64>","ciphertext":"<b64>"}}

# 4) Partner polls live projections (or Realtime-subscribes to stream_results)
GET /api/v1/projections?tenant_id=<uuid>&since=2026-07-17T00:00:00Z
Authorization: Bearer fjsvc_…
```

Workflow routing is config-only: send `content_type` /
`application/forjd-telemetry+v1` (example `threat_telemetry` YAML) or an
explicit `workflow_id`. Partner wire ids can be declared as
`aliases` on a workflow YAML (see `backend/workflows/README.md`) — do not
fork FORJD ingest per product.

For DEML and other partner backends, the canonical sealed batch contract is
`POST /api/v1/ingest/events:batch`. The Rust `/api/v1/ingest` batch edge is an
internal/compatibility outbox path, not the DEML-facing contract.
The FastAPI edge accepts at most 25 events and 8 MiB of JSON per request. It
rejects an oversized declared `Content-Length` before reading the body and
also enforces the same bound on chunked requests before JSON validation. Read
the deployed values from `GET /api/v1/capabilities`; treat `413` as a signal to
split and retry the batch with the same stable `client_event_id` values.
Acceptance atomically stores a ciphertext-free processing receipt containing
the exact ordered event-metadata group and validated workflow configuration
hash/version, plus a required tenant-scoped metadata-only audit event. Failure
to persist that compliance event rolls back both the sealed events and their
processing receipts. Processing is attempted synchronously, while replica-safe leased
workers recover a crash or restart. Poll each returned
`processing_batches[].status_path`; an exact duplicate retry wakes the original
pending/failed group instead of reinterpreting it under current workflow YAML.
`async_processing_available` remains false because FORJD does not yet promise a
general `202 Accepted` deferred-ingest contract.
Canonical API acceptance and the projector share a short database snapshot
fence so an older uncommitted API event cannot fall behind a committed tuple
checkpoint. Direct SQL/PostgREST inserts into `telemetry_events` bypass that
fence and are not a supported production ingest path.

Projection failures are handed off to a versioned DLQ in the same transaction
that advances the live cursor, so a poison page cannot block newer events.
Each failed source event remains individually replayable. A retry uses the
stored projection version and fails closed if the active workflow has drifted;
restore that version or perform a deliberate range replay under the new one.

## Scopes

| Scope | Allows |
|-------|--------|
| `ingest:write` | Sealed event / embedding ingest |
| `ingest:read` | List event metadata / stream results |
| `projections:read` | List projections / checkpoints |
| `projections:run` | Advance projection watermarks |
| `sessions:write` / `sessions:read` | Crypto session directory (register / list / revoke) |
| `replay:write` / `replay:read` | Replay sealed metadata; list / retry DLQ |
| `status:write` / `status:read` | Manage / list tenant status pages (public slug stays unauth) |
| `analytics:read` | Analytics overview |
| `analytics:write` | Trigger analytics aggregation (opt-in; not in default mint) |
| `exports:read` / `exports:write` | Tenant export jobs and artifacts |
| `vulnerabilities:read` / `vulnerabilities:write` | Vulnerability ledger CRUD |
| `integrations:write` | Register partner integration health checks |
| `siem:read` / `siem:write` | List/create PII-minimized normalized security signals and invoke correlation |
| `cases:read` / `cases:write` | List/create/update tenant incident cases |
| `playbooks:read` / `playbooks:write` | List/create/update tenant playbook definitions |
| `playbooks:execute` | Start idempotent playbook runs and acknowledge control-plane actions |
| `reports:read` / `reports:write` | List/create tenant report documents (partner user reports) |
| `threat-intel:read` | Read platform indicators plus indicators for the bound tenant |
| `threat-intel:write` | Tenant TAXII ingest (opt-in; never grants platform feed administration) |
| `ml:read` | Tenant ML reads (included in the default mint) |
| `ml:write` | Tenant ML writes/training (opt-in; not in default mint) |
| `tenants:erase` | Durable tenant erase (opt-in; not in default mint) |
| `*` | All scopes |

Default mint includes ingest, projections, sessions, replay, status,
`analytics:read`, `ml:read`, exports, vulnerabilities, integrations, normalized SIEM,
cases, playbook read/write/execute, report documents, and `threat-intel:read` (see
`DEFAULT_SCOPES` in `app/services/service_accounts.py`). `analytics:write`,
`threat-intel:write`, `ml:write`, and `tenants:erase` are allowlisted
but opt-in. Existing service-account rows keep their stored scopes until
rotated or recreated.

When `scopes` is omitted, the API resolves the backend's canonical
`DEFAULT_SCOPES`. Set `include_tenant_erase=true` to extend those defaults for a
dedicated account-deletion credential; it is false by default. The remint script
uses this body flag, so it never carries a second hard-coded default-scope list.

Humans use `tenant_members` roles (`owner` / `admin` / `member` / `viewer`) instead.

### Lost-response tenant-erase retry

An opaque service token with the opt-in `tenants:erase` scope deletes its own
`service_accounts` row as part of a successful tenant wipe. To make a response
lost after commit safely retryable, the durable erase receipt retains only that
authenticated token's 8-character lookup prefix and SHA-256 hash. The raw
`fjsvc_…` token, its scopes, and tenant data are never copied into the receipt;
the receipt has no tenant foreign key and therefore survives the wipe.

After completion, that deleted credential is accepted only for
`POST /api/v1/tenants/{the-same-tenant}/erase`. It can only return the existing
completed receipt. A different method, route, or tenant still returns `401`,
and a tombstone can never start or resume an incomplete erase. JWT-backed
service accounts do not use this opaque-credential retry mechanism.

## Normalized SIEM signal lane

The sealed ingest path remains the source of immutable encrypted evidence.
Content-aware SIEM work uses a separate, selectively disclosed contract:

```http
POST /api/v1/siem/signals
Authorization: Bearer fjsvc_…
Content-Type: application/json

{
  "tenant_id": "<uuid>",
  "client_signal_id": "guardduty:evt-001",
  "observed_at": "2026-07-19T12:00:00Z",
  "source": "guardduty",
  "category": "threat_intelligence",
  "signal_type": "network.malicious_ip",
  "severity": "high",
  "title": "Known malicious endpoint contacted",
  "confidence": 90,
  "observables": [{"type": "ipv4", "value": "198.51.100.10"}],
  "metadata": {"threat_match": true, "abuse_confidence_score": 90}
}
```

The request is strict and bounded. Unknown fields, raw/ciphertext fields,
credentials, email addresses, usernames, deeply nested/arbitrary metadata, and
unbounded observables are rejected. `(tenant_id, client_signal_id)` is unique;
an exact retry returns `duplicate=true`, while a different payload under the
same ID returns `409`. Use `GET /api/v1/siem/signals?tenant_id=…` with severity,
category, source, time, and limit filters.

## Cases and durable SOAR

- Cases: `GET/POST /api/v1/soc/cases`,
  `PATCH /api/v1/soc/cases/{case_id}`.
- Playbooks: `GET/POST /api/v1/playbooks`,
  `PATCH /api/v1/playbooks/{playbook_id}`.
- Execute: `POST /api/v1/playbooks/{playbook_id}/execute` with a caller
  `idempotency_key`; reusing the key with a different playbook/context returns
  `409`.
- Runs: `GET /api/v1/playbooks/runs?tenant_id=…`.
- Control-plane acknowledgement:
  `POST /api/v1/playbooks/runs/{run_id}/actions/{action_result_id}/ack`.
- Operator webhook retry:
  `POST /api/v1/playbooks/runs/{run_id}/actions/{action_result_id}/retry`.

Webhook actions report success only for a real 2xx response. Actions FORJD
cannot own (`email_alert`, `block_ip`, `revoke_api_key`) persist as
`awaiting_ack`; they never return fake success. Ordered execution pauses there
and resumes only after a successful acknowledgement. Run and action mutations
write required, metadata-only audit events; audit persistence failures propagate
and `audit_events` rows are database-enforced append-only.

Webhook delivery uses an immutable per-run ordered action snapshot and a stable
`Idempotency-Key` across every attempt. Network failures, `408`, `425`, `429`,
and `5xx` schedule at most five total attempts using exponential backoff. A
valid `Retry-After` is honored up to 300 seconds. Workers claim due actions with
leases and `FOR UPDATE SKIP LOCKED`; an expired lease can be reclaimed without
changing the delivery key. Redirects, configuration/egress rejection, and all
other `4xx` responses are terminal unless an owner/admin explicitly queues the
webhook retry endpoint. Control-plane `awaiting_ack` actions are never retried.
Exact ACK replays are idempotent; a conflicting ACK returns `409`.

`POST /api/v1/threat-intel/correlate` binds the complete operation to a
tenant-scoped idempotency key and request fingerprint. Exact replays heal the
same case and playbook receipts; changed content under the key returns `409`.
The legacy `/integrations/security-alert` bridge requires `client_alert_id` and
timezone-aware `observed_at` and uses the normalized signal fingerprint rather
than inserting a second non-idempotent alert path.

## Platform administration and outbound egress

Global abuse.ch refresh and platform-scoped TAXII ingest require a human JWT
with an admin-controlled Supabase claim:

```json
{"app_metadata":{"forjd":{"platform_admin":true}}}
```

`platform_role` of `admin` or `owner` under the same block is also accepted.
Tenant membership and `fjsvc_` tokens never grant platform administration.
Tenant TAXII ingest instead requires the bound tenant plus the opt-in
`threat-intel:write` scope.

In production, every custom TAXII collection and playbook webhook hostname must
match `OUTBOUND_HOST_ALLOWLIST`, a comma-separated set of exact hosts or
deliberate subdomain rules such as
`taxii.vendor.com,*.hooks.example.com`. Empty fails closed. Wildcards are DNS
boundary-aware: `*.hooks.example.com` matches `a.hooks.example.com`, but not the
apex or `evilhooks.example.com`. Custom egress also requires HTTPS, disables
redirects, uses bounded timeouts, rejects loopback/private/link-local/reserved
resolution results, caps TAXII responses at 2 MiB, and never reads webhook
response bodies.

### Crypto sessions and service principals

- `crypto_sessions.user_id` is an **opaque actor UUID** (human Auth `sub` or
  `service_accounts.id`). Apply `sql/017` so there is no FK to `auth.users`.
- Service principals with `sessions:write` may create, rotate, or revoke any
  session in their bound tenant (partner backends register device `key_id`s).
- Humans may only update/revoke sessions they own.

## Supabase M2M JWT (optional)

1. Create a Supabase Auth user dedicated to the subprocessor (not a human inbox).
2. Set `app_metadata.forjd`:

```json
{
  "principal_type": "service",
  "tenant_id": "<uuid>",
  "subprocessor": "partner-app",
  "scopes": [
    "ingest:write",
    "ingest:read",
    "projections:read",
    "projections:run",
    "sessions:write",
    "sessions:read",
    "replay:read",
    "replay:write",
    "status:read",
    "status:write",
    "analytics:read",
    "siem:read",
    "siem:write",
    "cases:read",
    "cases:write",
    "playbooks:read",
    "playbooks:write",
    "playbooks:execute",
    "threat-intel:read"
  ]
}
```

3. Register `POST /api/v1/service-accounts` with `auth_user_id` and
   `mint_opaque_token: false`.
4. Call FORJD with that user's access token. **DB row scopes win** over claims.

## Isolation invariants

- Service tokens cannot create tenants or mint other service accounts.
- Service tokens cannot access any tenant other than their bound `tenant_id`.
- Global `API_KEY` (if set) is a platform gate only — not a tenant credential.
- Rust `daemon_api_keys` remain a separate edge for `forjd-engine` ingest.
- Audit actors: humans = Supabase `sub`; services = `svc:<service_accounts.id>`.

## SQL

Apply `backend/sql/014_service_accounts.sql` after `013`, then
`015_realtime_and_consumer.sql`, `016_ml_supabase.sql`,
`017_service_principal_cutover.sql`, then
`018_partner_domain_scopes.sql` (exports / vulns / integrations /
domain scopes). `tenants:erase` is **allowlisted but opt-in** (`sql/019` /
`DEFAULT_SCOPES`); normalized SIEM/SOAR tables and scopes land in `sql/020`.
Apply `sql/021` for sealed-ingest/projection/replay reliability state, `sql/022`
for report documents and scopes, `sql/023` for durable exports, `sql/024`
for durable ingest-processing recovery, and `sql/025` for immutable SIEM/SOAR
replay snapshots and continuation recovery. Mint or rotate opaque `fjsvc_` tokens
after `017`–`025` (`scripts/remint_service_account.sh`; erase is opt-in via
`FORJD_INCLUDE_ERASE=1`) — existing rows keep previously stored scopes until
rotated. Durable partner deletion: `POST /api/v1/tenants/{id}/erase`.
Full deploy sequence: [`docs/PRODUCTION_DEPLOY.md`](../../docs/PRODUCTION_DEPLOY.md) and
[`docs/PRODUCTION_CHECKLIST.md`](../../docs/PRODUCTION_CHECKLIST.md).
