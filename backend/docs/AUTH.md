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
explicit `workflow_id`. Partner / legacy wire ids can be declared as
`aliases` on a workflow YAML (see `backend/workflows/README.md`) — do not
fork FORJD ingest per product.

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
| `*` | All scopes |

Default mint includes ingest, projections, sessions, replay, status, and
`analytics:read`. Existing service-account rows keep their stored scopes until
rotated or recreated.

Humans use `tenant_members` roles (`owner` / `admin` / `member` / `viewer`) instead.

### Crypto sessions and service principals

- `crypto_sessions.user_id` is an **opaque actor UUID** (human Auth `sub` or
  `service_accounts.id`). Apply `sql/016` so there is no FK to `auth.users`.
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
    "analytics:read"
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
`015_realtime_and_consumer.sql`, then `016_service_principal_cutover.sql`
(sessions actor id + expanded default scopes).
