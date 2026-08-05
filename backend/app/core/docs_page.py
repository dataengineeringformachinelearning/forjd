"""deml-ui Swagger UI page served at ``GET /docs``.

Self-hosts swagger-ui-dist under ``/static/vendor/`` and skins via deml-ui
plus ``forjd-backend.css`` — no jsDelivr or inline style blocks.
"""

from __future__ import annotations

from app.core.config import settings

# --- Swagger UI shell (deml-ui + owned backend chrome) ---
_DOCS_HTML = """\
<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project} — API docs</title>
<meta
  name="description"
  content="Interactive Swagger documentation for the FORJD sealed streaming API."
/>
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#35312D" />
<link rel="stylesheet" href="/static/vendor/swagger-ui-dist/swagger-ui.css" />
<link rel="stylesheet" href="/static/deml-ui.css" />
<link rel="stylesheet" href="/static/forjd-backend.css" />
</head>
<body class="forjd-backend-docs backend-swagger">
  <header class="forjd-backend-topbar">
    <a class="forjd-backend-brand" href="/">{project}</a>
    <nav aria-label="API documentation">
      <a href="https://dataengineeringformachinelearning.com/">community</a>
      <a href="/redoc">redoc</a>
      <a href="/openapi.json">openapi</a>
      <a href="/health">health</a>
      <a href="/ready">ready</a>
    </nav>
  </header>
  <main aria-label="FORJD interactive API documentation">
    <h1 class="forjd-sr-only">{project} interactive API documentation</h1>
    <div id="swagger-ui"></div>
  </main>
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
