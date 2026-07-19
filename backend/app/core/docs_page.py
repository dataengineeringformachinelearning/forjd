"""FJORD-themed Swagger UI page served at ``GET /`` and ``GET /docs``.

Embeds swagger-ui-dist with dark FJORD palette overrides so the interactive
API docs match the forjd-ui token system instead of the stock light theme.
"""

# ruff: noqa: E501 -- CSS overrides read better as one-line rules.

from __future__ import annotations

from app.core.config import settings

# --- Swagger UI shell (dark FJORD overrides on swagger-ui-dist) ---
_DOCS_HTML = """<!doctype html>
<html lang="en">
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
<style>
  :root {{
    --fj-bg: #0a0a0a; --fj-surface: #111111; --fj-surface-2: #1a1a1a;
    --fj-border: #222222; --fj-text: #f0f0f0; --fj-text-muted: #888888;
    --fj-primary: #00b4ff; --fj-primary-hover: #33c3ff; --fj-success: #00e6a6;
    --fj-warning: #ff9500; --fj-danger: #ff2d55; --fj-radius: 4px;
    --fj-sans: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
    --fj-mono: 'IBM Plex Mono', ui-monospace, monospace;
  }}
  html, body {{ margin: 0; background: var(--fj-bg); }}

  /* --- FORJD header bar --- */
  .fj-topbar {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.85rem 1.5rem; background: var(--fj-surface);
    border-bottom: 1px solid var(--fj-border); font-family: var(--fj-sans);
  }}
  .fj-topbar a {{ text-decoration: none; }}
  .fj-topbar .fj-brand {{
    font-family: var(--fj-mono); letter-spacing: 0.12em; text-transform: uppercase;
    font-size: 0.8rem; color: var(--fj-primary); font-weight: 600;
  }}
  .fj-topbar nav {{ display: flex; gap: 1rem; }}
  .fj-topbar nav a {{
    color: var(--fj-text-muted); font-size: 0.8125rem; font-family: var(--fj-mono);
  }}
  .fj-topbar nav a:hover {{ color: var(--fj-primary); }}

  /* --- Swagger UI dark overrides (FJORD palette) --- */
  body {{ font-family: var(--fj-sans); }}
  .swagger-ui {{ color: var(--fj-text); }}
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
  .swagger-ui .auth-container label, .swagger-ui .btn {{ color: var(--fj-text); }}
  .swagger-ui .info .base-url, .swagger-ui .info li, .swagger-ui .info p,
  .swagger-ui .info a, .swagger-ui .parameter__in,
  .swagger-ui .prop-format, .swagger-ui .model .property.primitive {{ color: var(--fj-text-muted); }}
  .swagger-ui .info a {{ color: var(--fj-primary); }}
  .swagger-ui .scheme-container {{ background: var(--fj-surface); box-shadow: none; border-bottom: 1px solid var(--fj-border); }}
  .swagger-ui .opblock-tag {{ border-bottom: 1px solid var(--fj-border); }}
  .swagger-ui .opblock {{
    background: var(--fj-surface); border: 1px solid var(--fj-border);
    border-radius: var(--fj-radius); box-shadow: none;
  }}
  .swagger-ui .opblock .opblock-section-header {{ background: var(--fj-surface-2); box-shadow: none; }}
  .swagger-ui .opblock .opblock-section-header h4, .swagger-ui .opblock .opblock-section-header label {{ color: var(--fj-text); }}
  .swagger-ui .opblock.opblock-get .opblock-summary-method {{ background: var(--fj-primary); color: #0a0a0a; }}
  .swagger-ui .opblock.opblock-post .opblock-summary-method {{ background: var(--fj-success); color: #0a0a0a; }}
  .swagger-ui .opblock.opblock-delete .opblock-summary-method {{ background: var(--fj-danger); }}
  .swagger-ui .opblock.opblock-put .opblock-summary-method,
  .swagger-ui .opblock.opblock-patch .opblock-summary-method {{ background: var(--fj-warning); color: #0a0a0a; }}
  .swagger-ui .opblock.opblock-get {{ border-color: var(--fj-border); background: var(--fj-surface); }}
  .swagger-ui .opblock.opblock-post {{ border-color: var(--fj-border); background: var(--fj-surface); }}
  .swagger-ui .opblock.opblock-delete {{ border-color: var(--fj-border); background: var(--fj-surface); }}
  .swagger-ui .opblock.opblock-put, .swagger-ui .opblock.opblock-patch {{ border-color: var(--fj-border); background: var(--fj-surface); }}
  .swagger-ui .opblock .opblock-summary {{ border-color: var(--fj-border); }}
  .swagger-ui .btn {{ border-color: var(--fj-border); box-shadow: none; }}
  .swagger-ui .btn.authorize {{ border-color: var(--fj-primary); color: var(--fj-primary); }}
  .swagger-ui .btn.authorize svg {{ fill: var(--fj-primary); }}
  .swagger-ui .btn.execute {{ background: var(--fj-primary); border-color: var(--fj-primary); color: #0a0a0a; }}
  .swagger-ui select, .swagger-ui input[type=text], .swagger-ui input[type=password],
  .swagger-ui input[type=email], .swagger-ui textarea {{
    background: var(--fj-surface-2); color: var(--fj-text); border: 1px solid var(--fj-border);
  }}
  .swagger-ui .dialog-ux .modal-ux {{ background: var(--fj-surface); border: 1px solid var(--fj-border); }}
  .swagger-ui .dialog-ux .modal-ux-header {{ border-bottom: 1px solid var(--fj-border); }}
  .swagger-ui section.models {{ border: 1px solid var(--fj-border); }}
  .swagger-ui section.models.is-open h4 {{ border-bottom: 1px solid var(--fj-border); }}
  .swagger-ui section.models .model-container {{ background: var(--fj-surface); }}
  .swagger-ui .model-box {{ background: var(--fj-surface-2); }}
  .swagger-ui .copy-to-clipboard {{ background: var(--fj-surface-2); }}
  .swagger-ui .responses-inner {{ color: var(--fj-text-muted); }}
  .swagger-ui .markdown p, .swagger-ui .markdown li, .swagger-ui .renderedMarkdown p {{ color: var(--fj-text-muted); }}
  .swagger-ui .markdown code, .swagger-ui code {{ color: var(--fj-success); font-family: var(--fj-mono); }}
  .swagger-ui svg:not(:root) {{ fill: var(--fj-text-muted); }}
  .swagger-ui .expand-operation svg, .swagger-ui .expand-methods svg {{ fill: var(--fj-text-muted); }}
  .swagger-ui .loading-container .loading::after {{ color: var(--fj-text-muted); }}
</style>
</head>
<body>
  <header class="fj-topbar">
    <a href="/"><span class="fj-brand">{project}</span></a>
    <nav>
      <a href="https://forjd.co">product</a>
      <a href="/redoc">redoc</a>
      <a href="/openapi.json">openapi</a>
      <a href="/health">health</a>
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
    """Return the FJORD-themed Swagger UI HTML."""
    return _DOCS_HTML.format(
        project=settings.PROJECT_NAME.upper(),
        openapi_url="/openapi.json",
    )
