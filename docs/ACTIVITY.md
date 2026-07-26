# Activity and audit logs

Two layers — do not conflate them.

| Layer | Where | Purpose |
|-------|--------|---------|
| **Suite activity** (this doc) | Browser `suite-activity-v1` | Soft-chrome important actions on this device |
| **Server audit** | FORJD `audit_events` · DEML `AuditLog` | Compliance / privileged API writes (metadata-only) |

## Suite activity (ADR-0027)

| Item | Detail |
|------|--------|
| Storage | `suite-activity-v1` (JSON ring buffer, max 50) |
| Sync | Cross-tab via `storage`; same-tab via `suite-activity-change` |
| UI | Preferences → **Recent activity** (`forjd-activity-list` / `viking-activity-list`) |
| ADR | [0027](adr/0027-client-activity-log.md) |

### Recorded kinds (v1)

| Kind | When |
|------|------|
| `preferences.theme` | Theme preference changes |
| `preferences.export` / `preferences.import` | Suite data pack transfer |
| `preferences.reset` | Reset all preferences |
| `disclosure.reset` | Reset advanced sections |
| `search.clear` | Clear search history |
| `onboarding.complete` / `onboarding.dismiss` | Checklist / wizard finish |

### Never store

`fjsvc_`, JWTs, API keys, ciphertext, request bodies, or sealed event content.
Sensitive-looking labels are rejected.

## Server audit (existing — not this UI)

- FORJD: `backend/app/services/audit.py` → `audit_events` (append-only, RLS)
- DEML: `AuditLog` / `log_audit_event` / `record_forjd_audit` for BFF outcomes
- No product list UI yet; do not invent a parallel Postgres audit system for soft chrome
