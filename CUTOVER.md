# FORJD production cutover checklist

Safe sequence for taking FORJD as the exclusive sealed streaming engine for
partner subprocessors (including DEML). FORJD stays **universal** — partner
wire names belong only in YAML `aliases` or in the partner’s own BFF rewrite.

## Preflight

1. Apply SQL in order: `003` → `016` (`backend/sql/README.md`).
2. Confirm production forces RLS + crypto-session binding (`ENVIRONMENT=prod`).
3. Mint (or remint) tenant `fjsvc_` service accounts **after** `016` so scopes
   include sessions, replay/DLQ, status, and `analytics:read`.
4. Verify isolation gates:
   - `service_role` JWT rejected on application routes
   - cross-tenant `tenant_id` → `403`
   - sealed ingest stores ciphertext only (no plaintext columns)
5. Deploy workflow YAML for the partner’s content types. Prefer canonical ids
   (`threat_telemetry` / `threat.*`). If the partner still sends legacy wire
   ids, copy `workflows/examples/partner_legacy_aliases.example.yaml` into an
   enabled partner-local overlay under `workflows/` — never hardcode product
   names in `app/` or `engine/`.
6. Staging smoke: register session → sealed ingest → projections list →
   replay/DLQ read (service token only).

## Cutover sequence

| Phase | Action | Rollback |
|-------|--------|----------|
| **0 — Dual-write (optional)** | Partner BFF may write to legacy bus **and** FORJD while comparing counts. FORJD remains source of truth for new sealed events. | Stop FORJD writes; keep legacy. |
| **1 — Read switch** | Partner BFF reads projections / analytics / status from FORJD only. | Flip partner read flag back to legacy (if still available). |
| **2 — Write switch** | Partner stops legacy ingest; sealed path is FORJD-only. | Re-enable legacy writers; keep FORJD ingest for later reconcile. |
| **3 — Decommission** | Remove partner local brokers, OLAP, workers. Revoke unused credentials. | Redeploy retired stack from last known-good image (costly). |

## Security confirmation

- E2EE: AES-256-GCM envelopes; AAD binds `tenant_id|client_event_id`; nonce
  uniqueness (`sql/013`); session revoke blocks ingest.
- Tenant isolation: RLS + `require_tenant_access` (human member **or** scoped
  `fjsvc_`); service tokens cannot create tenants or mint peers.
- Subprocessor model: partner end-user tokens (e.g. Firebase) never reach FORJD.

## Post-cutover

- Monitor ingest 4xx/5xx, DLQ depth, projection lag, session register failures.
- Rotate `fjsvc_` on a schedule; store only secret references at the partner.
- Open ops ticket for tenant erase until an idempotent erase API ships.
