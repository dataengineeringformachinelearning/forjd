"""Static landing page for the FORJD API root.

A single self-contained HTML document (FJORD dark palette, no external assets)
that introduces the engine and links to the interactive API docs. Rendered at
``GET /`` so the bare backend URL is a modern page rather than a 404.
"""

# ruff: noqa: E501 -- SEO metadata is kept as readable one-line HTML attributes.

from __future__ import annotations

from app.core.config import settings

# --- FJORD palette (mirrors frontend/src/styles.scss tokens) ---
_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project} — universal secure streaming engine</title>
<meta name="description"
      content="FORJD API for sealed ingest, configurable workflows, durable projections, analytics, replay, and machine learning." />
<meta name="robots" content="index, follow, max-image-preview:large" />
<link rel="canonical" href="https://backend.forjd.co/" />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta property="og:type" content="website" />
<meta property="og:url" content="https://backend.forjd.co/" />
<meta property="og:title" content="FORJD API — Universal Secure Streaming Engine" />
<meta property="og:description"
      content="Secure streaming APIs for sealed ingest, workflows, projections, analytics, replay, and machine learning." />
<meta property="og:image" content="https://backend.forjd.co/static/forjd-social.png" />
<meta property="og:image:type" content="image/png" />
<meta property="og:image:width" content="1280" />
<meta property="og:image:height" content="720" />
<meta property="og:image:alt" content="FORJD secure streaming engine" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="FORJD API — Universal Secure Streaming Engine" />
<meta name="twitter:description"
      content="Secure streaming APIs for sealed ingest, workflows, projections, analytics, replay, and machine learning." />
<meta name="twitter:image" content="https://backend.forjd.co/static/forjd-social.png" />
<meta name="theme-color" content="#0a0a0a" />
<style>
  :root {{
    --fj-bg: #0a0a0a; --fj-surface: #111111; --fj-surface-2: #1a1a1a;
    --fj-border: #222222; --fj-text: #f0f0f0; --fj-text-muted: #888888;
    --fj-primary: #00b4ff; --fj-primary-hover: #33c3ff; --fj-success: #00e6a6;
    --fj-danger: #ff2d55; --fj-radius: 4px;
    --fj-sans: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
    --fj-mono: 'IBM Plex Mono', ui-monospace, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; background: var(--fj-bg); color: var(--fj-text);
    font-family: var(--fj-sans); line-height: 1.5;
    display: flex; align-items: center; justify-content: center; padding: 2rem;
  }}
  .card {{
    width: 100%; max-width: 640px; background: var(--fj-surface);
    border: 1px solid var(--fj-border); border-radius: var(--fj-radius);
    padding: 2.5rem;
  }}
  .brand {{
    font-family: var(--fj-mono); letter-spacing: 0.12em; text-transform: uppercase;
    font-size: 0.75rem; color: var(--fj-primary); margin: 0 0 0.75rem;
  }}
  h1 {{ margin: 0 0 0.75rem; font-size: clamp(1.75rem, 4vw, 2.25rem); letter-spacing: -0.02em; }}
  p.lede {{ margin: 0 0 1.75rem; color: var(--fj-text-muted); max-width: 48ch; }}
  .actions {{ display: flex; flex-wrap: wrap; gap: 0.75rem; margin-bottom: 2rem; }}
  a.btn {{
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.6rem 1.1rem; border-radius: var(--fj-radius); text-decoration: none;
    font-weight: 600; font-size: 0.9rem; border: 1px solid transparent;
    transition: background 0.15s ease, border-color 0.15s ease;
  }}
  a.btn--primary {{ background: var(--fj-primary); color: #0a0a0a; }}
  a.btn--primary:hover {{ background: var(--fj-primary-hover); }}
  a.btn--ghost {{ border-color: var(--fj-border); color: var(--fj-text); }}
  a.btn--ghost:hover {{ border-color: var(--fj-primary); color: var(--fj-primary); }}
  .meta {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 0.75rem; border-top: 1px solid var(--fj-border); padding-top: 1.5rem;
  }}
  .meta div {{ font-size: 0.8125rem; }}
  .meta span {{ display: block; color: var(--fj-text-muted); font-family: var(--fj-mono); }}
  .meta code {{ color: var(--fj-success); font-family: var(--fj-mono); }}
</style>
</head>
<body>
  <main class="card">
    <p class="brand">{project}</p>
    <h1>Universal secure streaming engine</h1>
    <p class="lede">
      Sealed end-to-end encrypted ingest, configurable YAML workflows, durable
      projections, replay/DLQ, and tenant-scoped analytics — driven by a Rust
      hot-path and FastAPI control plane.
    </p>
    <div class="actions">
      <a class="btn btn--primary" href="/docs">API docs</a>
      <a class="btn btn--ghost" href="/redoc">ReDoc</a>
    </div>
    <div class="meta">
      <div><span>version</span><code>{version}</code></div>
      <div><span>environment</span><code>{environment}</code></div>
      <div><span>api base</span><code>{api}</code></div>
    </div>
  </main>
</body>
</html>"""


def render_landing() -> str:
    """Return the FORJD API landing page HTML."""
    return _LANDING_HTML.format(
        project=settings.PROJECT_NAME.upper(),
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        api=settings.API_V1_STR,
    )
