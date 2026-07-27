"""Suite-themed ReDoc shell served at ``GET /redoc``.

Self-hosts redoc under ``/static/vendor/`` — no jsDelivr CDN.
"""

from __future__ import annotations

from html import escape

from app.core.config import settings

# --- ReDoc shell (suite-backend topbar + suite-apidocs) ---
_REDOC_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project} — ReDoc</title>
<meta name="description" content="ReDoc reference for the FORJD secure streaming API." />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#0a0a0a" />
<link rel="stylesheet" href="/static/suite-fonts.css" />
<link rel="stylesheet" href="/static/suite-tokens.css" />
<link rel="stylesheet" href="/static/suite-components.css" />
<link rel="stylesheet" href="/static/suite-backend.css" />
<link rel="stylesheet" href="/static/suite-apidocs.css" />
<link rel="stylesheet" href="/static/forjd-apidocs.css" />
</head>
<body class="suite-backend-docs backend-redoc">
  <header class="suite-backend-topbar backend-docs-topbar fj-topbar">
    <a href="https://forjd.co/"><span class="suite-backend-brand backend-docs-brand fj-brand">{project}</span></a>
    <nav aria-label="API documentation">
      <a href="https://forjd.co/">product</a>
      <a href="/docs">swagger</a>
      <a href="/openapi.json">openapi</a>
      <a href="/health">health</a>
      <a href="/ready">ready</a>
    </nav>
  </header>
  <main id="redoc-container" aria-label="FORJD API reference"></main>
  <script src="/static/vendor/redoc/redoc.standalone.js"></script>
  <script
    src="/static/redoc-init.js"
    data-openapi-url="/openapi.json"
    data-csp-nonce="{nonce}"
  ></script>
</body>
</html>"""


def render_redoc(*, nonce: str | None = None) -> str:
    """Return the suite-themed ReDoc HTML."""
    return _REDOC_HTML.format(
        project=settings.PROJECT_NAME.upper(),
        nonce=escape(nonce or "", quote=True),
    )
