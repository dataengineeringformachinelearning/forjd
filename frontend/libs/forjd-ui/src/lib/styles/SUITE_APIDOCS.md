# Suite API docs — owned Swagger / ReDoc chrome

**Styles:** [`suite-apidocs.css`](./suite-apidocs.css)
**Depends on:** suite-tokens → suite-components → suite-backend
**Hosts:** `backend.forjd.co/docs` + `/redoc`, `backend.deml.app/api/v1/docs` + `/api/v1/redoc`

## Goal

Interactive API docs share suite void chrome — quiet method chips, Inter, electric accents — without CDN skins or inline `<style>` blocks.

## Load order

```
# FORJD
suite-fonts → suite-tokens → suite-components → suite-backend → suite-apidocs
+ vendor/swagger-ui-dist/* or vendor/redoc/*

# DEML
vendor swagger-ui.css → viking-ui.css → suite-apidocs.css
+ vendor/swagger-ui-dist/* or vendor/redoc/*
```

## Rules

1. **Self-host** swagger-ui-dist and redoc under `backend/static/vendor/` (pinned `VERSION` files).
2. **No jsDelivr** for swagger/redoc in HTML templates (CSP may still allow jsDelivr for Algolia / published widgets).
3. **Token-only** colors in `suite-apidocs.css`.
4. Refresh vendors: `bash scripts/vendor_apidocs.sh` in each repo after bumping pins.
5. After editing SoT CSS, copy to DEML `backend/static/suite-apidocs.css` and run FORJD `npm run sync:suite`.

## Verify

```bash
# FORJD
grep -RIn 'cdn.jsdelivr.net/npm/swagger\|cdn.jsdelivr.net/npm/redoc' backend/app || true
test -f backend/static/suite-apidocs.css
test -f backend/static/vendor/swagger-ui-dist/swagger-ui-bundle.js

# DEML
grep -RIn 'cdn.jsdelivr.net/npm/swagger\|cdn.jsdelivr.net/npm/redoc' backend/templates || true
test -f backend/static/suite-apidocs.css
node --test packages/viking-ui/test/swagger-theme-contract.test.mjs
```
