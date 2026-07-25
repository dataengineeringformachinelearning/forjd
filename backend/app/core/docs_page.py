"""Suite-themed Swagger UI page served at ``GET /docs``.

Embeds swagger-ui-dist with dark suite palette overrides. Topbar chrome
comes from suite-backend.css — no stock light Swagger theme.
"""

# ruff: noqa: E501 -- CSS overrides read better as one-line rules.

from __future__ import annotations

from app.core.config import settings

# --- Swagger UI shell (suite tokens + suite-backend topbar) ---
_DOCS_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project} — API docs</title>
<meta name="description" content="Interactive Swagger documentation for the FORJD secure streaming API." />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#0a0a0a" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css" />
<link rel="stylesheet" href="/static/suite-tokens.css" />
<link rel="stylesheet" href="/static/suite-components.css" />
<link rel="stylesheet" href="/static/suite-backend.css" />
<style>
  /* Swagger widget overrides only — shell chrome from suite-backend.css */
  .swagger-ui {{ color: var(--suite-ink); font-family: var(--suite-font-sans); }}
  .swagger-ui .topbar {{ display: none; }}
  .swagger-ui .info .title, .swagger-ui .info h1, .swagger-ui .info h2,
  .swagger-ui .info h3, .swagger-ui .info h4, .swagger-ui .info h5,
  .swagger-ui .opblock-tag, .swagger-ui .opblock .opblock-summary-description,
  .swagger-ui table thead tr th, .swagger-ui table thead tr td,
  .swagger-ui .parameter__name, .swagger-ui .parameter__type,
  .swagger-ui .response-col_status, .swagger-ui .response-col_links,
  .swagger-ui .responses-inner h4, .swagger-ui .responses-inner h5,
  .swagger-ui .opblock-description-wrapper p, .swagger-ui .opblock-title_normal p,
  .swagger-ui .model, .swagger-ui .model-title, .swagger-ui label,
  .swagger-ui .tab li, .swagger-ui section.models h4, .swagger-ui .scheme-container .schemes-title,
  .swagger-ui .dialog-ux .modal-ux-content p, .swagger-ui .dialog-ux .modal-ux-header h3,
  .swagger-ui .auth-container label, .swagger-ui .btn {{ color: var(--suite-ink); }}
  .swagger-ui .info .base-url, .swagger-ui .info li, .swagger-ui .info p,
  .swagger-ui .info a, .swagger-ui .parameter__in,
  .swagger-ui .prop-format, .swagger-ui .model .property.primitive {{ color: var(--suite-ink-muted); }}
  .swagger-ui .info a {{ color: var(--suite-primary); }}
  .swagger-ui .scheme-container {{ background: var(--suite-surface); box-shadow: none; border-bottom: 1px solid var(--suite-border); }}
  .swagger-ui .opblock-tag {{ border-bottom: 1px solid var(--suite-border); }}
  .swagger-ui .opblock {{
    background: var(--suite-surface); border: 1px solid var(--suite-border);
    border-radius: var(--suite-radius); box-shadow: none;
  }}
  .swagger-ui .opblock .opblock-section-header {{ background: var(--suite-surface-2); box-shadow: none; }}
  .swagger-ui .opblock .opblock-section-header h4, .swagger-ui .opblock .opblock-section-header label {{ color: var(--suite-ink); }}
  .swagger-ui .opblock.opblock-get .opblock-summary-method {{ background: var(--suite-primary); color: var(--suite-ink-on-primary); }}
  .swagger-ui .opblock.opblock-post .opblock-summary-method {{ background: var(--suite-success); color: var(--suite-ink-on-primary); }}
  .swagger-ui .opblock.opblock-delete .opblock-summary-method {{ background: var(--suite-danger); color: var(--suite-ink-on-primary); }}
  .swagger-ui .opblock.opblock-put .opblock-summary-method,
  .swagger-ui .opblock.opblock-patch .opblock-summary-method {{ background: var(--suite-warning); color: var(--suite-ink-inverse); }}
  .swagger-ui .opblock.opblock-get,
  .swagger-ui .opblock.opblock-post,
  .swagger-ui .opblock.opblock-delete,
  .swagger-ui .opblock.opblock-put,
  .swagger-ui .opblock.opblock-patch {{ border-color: var(--suite-border); background: var(--suite-surface); }}
  .swagger-ui .opblock .opblock-summary {{ border-color: var(--suite-border); }}
  .swagger-ui .btn {{ border-color: var(--suite-border); box-shadow: none; }}
  .swagger-ui .btn.authorize {{ border-color: var(--suite-primary); color: var(--suite-primary); }}
  .swagger-ui .btn.authorize svg {{ fill: var(--suite-primary); }}
  .swagger-ui .btn.execute {{ background: var(--suite-primary); border-color: var(--suite-primary); color: var(--suite-ink-on-primary); }}
  .swagger-ui select, .swagger-ui input[type=text], .swagger-ui input[type=password],
  .swagger-ui input[type=email], .swagger-ui textarea {{
    background: var(--suite-surface-2); color: var(--suite-ink); border: 1px solid var(--suite-border);
  }}
  .swagger-ui .dialog-ux .modal-ux {{ background: var(--suite-surface); border: 1px solid var(--suite-border); }}
  .swagger-ui .dialog-ux .modal-ux-header {{ border-bottom: 1px solid var(--suite-border); }}
  .swagger-ui section.models {{ border: 1px solid var(--suite-border); }}
  .swagger-ui section.models.is-open h4 {{ border-bottom: 1px solid var(--suite-border); }}
  .swagger-ui section.models .model-container {{ background: var(--suite-surface); }}
  .swagger-ui .model-box {{ background: var(--suite-surface-2); }}
  .swagger-ui .copy-to-clipboard {{ background: var(--suite-surface-2); }}
  .swagger-ui .responses-inner {{ color: var(--suite-ink-muted); }}
  .swagger-ui .markdown p, .swagger-ui .markdown li, .swagger-ui .renderedMarkdown p {{ color: var(--suite-ink-muted); }}
  .swagger-ui .markdown code, .swagger-ui code {{ color: var(--suite-success); font-family: var(--suite-font-mono); }}
  .swagger-ui svg:not(:root) {{ fill: var(--suite-ink-muted); }}
  .swagger-ui .expand-operation svg, .swagger-ui .expand-methods svg {{ fill: var(--suite-ink-muted); }}
  .swagger-ui .loading-container .loading::after {{ color: var(--suite-ink-muted); }}
</style>
</head>
<body class="suite-backend-docs backend-swagger">
  <header class="suite-backend-topbar backend-docs-topbar fj-topbar">
    <a href="https://forjd.co/"><span class="suite-backend-brand backend-docs-brand fj-brand">{project}</span></a>
    <nav aria-label="API documentation">
      <a href="https://forjd.co/">product</a>
      <a href="/redoc">redoc</a>
      <a href="/openapi.json">openapi</a>
      <a href="/health">health</a>
      <a href="/ready">ready</a>
    </nav>
  </header>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({{
      url: '{openapi_url}',
      dom_id: '#swagger-ui',
      presets: [SwaggerUIBundle.presets.apis],
      layout: 'BaseLayout',
      deepLinking: true,
      displayRequestDuration: true,
      defaultModelsExpandDepth: 0,
    }});
  </script>
</body>
</html>"""


def render_docs() -> str:
    """Return the suite-themed Swagger UI HTML."""
    return _DOCS_HTML.format(
        project=settings.PROJECT_NAME.upper(),
        openapi_url="/openapi.json",
    )
