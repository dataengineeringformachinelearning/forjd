# FORJD Authentication & Subprocessor Model

FORJD is a **universal secure streaming backend**. It serves:

1. **Enterprise / direct users** — humans on Supabase Auth (FORJD console / API).
2. **Trusted subprocessors** — machine callers such as the DEML Django app, which
   manages its **own** end-user identity (Firebase) and calls FORJD with a
   **tenant-scoped service token**.

FORJD never accepts DEML (or other SaaS) end-user tokens.

## Principal kinds

| Kind | Credential | Tenant binding |
|------|------------|----------------|
| `user` | Supabase Auth access JWT (`role=authenticated`) | Via `tenant_members` (multi-tenant) |
| `service` | Opaque `fjsvc_<prefix>_<secret>` **or** Supabase JWT with `app_metadata.forjd.principal_type=service` | Hard-bound to one `service_accounts.tenant_id` |

Resolved in `app.core.auth.AuthUser` (`kind`, `scopes`, `subprocessor`, `actor_id`).

**Rejected:** Supabase `service_role` JWTs on application routes (too privileged).

## Subprocessor flow (DEML example)

```
DEML end-user ──Firebase──► DEML Django
                              │
                              │ Authorization: Bearer fjsvc_…
                              │ (tenant-scoped service account)
                              ▼
                           FORJD API
                     ingest / projections
                              │
                              ▼
                     telemetry_events (ciphertext)
```

1. Enterprise admin creates a FORJD tenant and membership (human JWT).
2. Admin mints a service account: `POST /api/v1/service-accounts` with
   `subprocessor: "deml"` (token returned **once**).
3. DEML stores the token as a secret; every call includes
   `Authorization: Bearer fjsvc_…` and the same `tenant_id` in the body/query.
4. FORJD enforces: token → single tenant + scopes (`ingest:write`, …).
5. Payloads remain E2EE: DEML (or its clients) seal with AES-256-GCM; FORJD
   stores ciphertext only. Register `crypto_sessions` with a human or
   `sessions:write` service scope before ingest when `REQUIRE_CRYPTO_SESSION=true`.

## Scopes

| Scope | Allows |
|-------|--------|
| `ingest:write` | Sealed event / embedding ingest |
| `ingest:read` | List event metadata / stream results |
| `projections:read` | List projections / checkpoints |
| `projections:run` | Advance projection watermarks |
| `sessions:write` / `sessions:read` | Crypto session directory (optional) |
| `*` | All scopes |

Humans use `tenant_members` roles (`owner` / `admin` / `member` / `viewer`) instead.

## Supabase M2M JWT (optional)

1. Create a Supabase Auth user dedicated to the subprocessor (not a human inbox).
2. Set `app_metadata.forjd`:

```json
{
  "principal_type": "service",
  "tenant_id": "<uuid>",
  "subprocessor": "deml",
  "scopes": ["ingest:write", "ingest:read", "projections:read", "projections:run"]
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

Apply `backend/sql/014_service_accounts.sql` after `013`.
