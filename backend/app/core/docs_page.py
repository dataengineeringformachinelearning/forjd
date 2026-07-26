"""Suite-themed Swagger UI page served at ``GET /docs``.

Self-hosts swagger-ui-dist under ``/static/vendor/`` and skins via
``suite-apidocs.css`` — no jsDelivr, no inline style blocks.
"""

from __future__ import annotations

from app.core.config import settings

# --- Swagger UI shell (suite tokens + owned apidocs skin) ---
_DOCS_HTML = """\
<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project} — API docs</title>
<meta
  name="description"
  content="Interactive Swagger documentation for the FORJD secure streaming API."
/>
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#0a0a0a" />
<link rel="stylesheet" href="/static/vendor/swagger-ui-dist/swagger-ui.css" />
<link rel="stylesheet" href="/static/suite-fonts.css" />
<link rel="stylesheet" href="/static/suite-tokens.css" />
<link rel="stylesheet" href="/static/suite-components.css" />
<link rel="stylesheet" href="/static/suite-backend.css" />
<link rel="stylesheet" href="/static/suite-apidocs.css" />
</head>
<body class="suite-backend-docs backend-swagger">
  <header class="suite-backend-topbar backend-docs-topbar fj-topbar">
    <a href="https://forjd.co/">
      <span class="suite-backend-brand backend-docs-brand fj-brand">{project}</span>
    </a>
    <nav aria-label="API documentation">
      <a href="https://forjd.co/">product</a>
      <a href="/redoc">redoc</a>
      <a href="/openapi.json">openapi</a>
      <a href="/health">health</a>
      <a href="/ready">ready</a>
    </nav>
  </header>
  <div id="swagger-ui"></div>
  <script src="/static/vendor/swagger-ui-dist/swagger-ui-bundle.js"></script>
  <script src="/static/docs-swagger-init.js" data-openapi-url="{openapi_url}"></script>
</body>
</html>
"""


def render_docs(*, openapi_url: str = "/openapi.json") -> str:
    """Return the self-hosted Swagger UI HTML shell."""
    return _DOCS_HTML.format(
        project=settings.PROJECT_NAME,
        openapi_url=openapi_url,
    )
