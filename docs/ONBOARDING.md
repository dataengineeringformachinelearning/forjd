# Suite onboarding / empty guidance

First-time guidance for **forjd.co** (partner deploy sequence) and **deml.app**
(status-page wizard + checklist).

| Item | Detail |
|------|--------|
| Storage | `suite-onboarding-v1` (JSON) |
| Sync | Cross-tab via `storage`; same-tab via `suite-onboarding-change` |
| Checklist | `forjd-onboarding-checklist` / `viking-onboarding-checklist` |
| Empty | `forjd-empty` / `viking-empty-state` + `SUITE_EMPTY_GUIDANCE_EYEBROW` |
| ADR | [0025](adr/0025-onboarding-empty-guidance.md) |

## Fields (v1)

| Field | Values | Notes |
|-------|--------|--------|
| `dismissed` | boolean | User hid the guide without finishing |
| `completed` | boolean | User finished the flow |
| `completedSteps` | string[] | Stable step ids (max 32) |
| `activeFlow` | `deml-status` \| `forjd-partner` \| null | Which journey is in focus |
| `updatedAt` | epoch ms | Last-write-wins across tabs |

## Flows

| Flow | Surface | Steps |
|------|---------|--------|
| `deml-status` | DEML wizard + dashboard checklist | `welcome`, `site`, `endpoint`, `publish`, `done` |
| `forjd-partner` | FORJD landing sequence | `bind`, `seal`, `project`, `operate` |

## Empty-state law

Do **not** invent a second empty primitive. Use the suite empty component with
eyebrow **`Getting started`** (`SUITE_EMPTY_GUIDANCE_EYEBROW`) and project
primary/secondary CTAs (open wizard, go to Sites, docs link).

## Portable transfer

Onboarding state is included in the suite data pack (ADR-0026) from Preferences
→ Export / import. See [`docs/PREFERENCES.md`](PREFERENCES.md).

## Never store

`fjsvc_`, JWTs, API keys, session/auth flags, or any ciphertext.
