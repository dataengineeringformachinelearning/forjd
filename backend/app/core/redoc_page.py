"""FJORD-themed ReDoc shell served at ``GET /redoc``."""

# ruff: noqa: E501 -- compact HTML/CSS shell

from __future__ import annotations

from app.core.config import settings

# --- ReDoc shell (Void / Operator; mirrors docs topbar) ---
_REDOC_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project} — ReDoc</title>
<meta name="description" content="ReDoc reference for the FORJD secure streaming API." />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#0a0a0a" />
<style>
  :root {{
    color-scheme: dark;
    --fj-bg: #0a0a0a; --fj-surface: #111111; --fj-border: #222222;
    --fj-text: #f0f0f0; --fj-text-muted: #888888; --fj-primary: #00b4ff;
    --fj-font-sans: system-ui, -apple-system, 'Segoe UI', sans-serif;
    --fj-font-mono: ui-monospace, 'SFMono-Regular', Consolas, monospace;
  }}
  html, body {{ margin: 0; background: var(--fj-bg); }}
  .fj-topbar {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.85rem 1.5rem; background: var(--fj-surface);
    border-bottom: 1px solid var(--fj-border); font-family: var(--fj-font-sans);
  }}
  .fj-topbar a {{ text-decoration: none; }}
  .fj-topbar .fj-brand {{
    font-family: var(--fj-font-mono); letter-spacing: 0.12em; text-transform: uppercase;
    font-size: 0.8rem; color: var(--fj-primary); font-weight: 600;
  }}
  .fj-topbar nav {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .fj-topbar nav a {{
    color: var(--fj-text-muted); font-size: 0.8125rem; font-family: var(--fj-font-mono);
  }}
  .fj-topbar nav a:hover {{ color: var(--fj-primary); }}
  redoc {{ display: block; }}
</style>
</head>
<body>
  <header class="fj-topbar">
    <a href="https://forjd.co/"><span class="fj-brand">{project}</span></a>
    <nav>
      <a href="https://forjd.co/">product</a>
      <a href="/docs">swagger</a>
      <a href="/openapi.json">openapi</a>
      <a href="/health">health</a>
      <a href="/ready">ready</a>
    </nav>
  </header>
  <!-- nosemgrep: html.security.audit.missing-integrity.missing-integrity — ReDoc CDN; major version pinned -->
  <redoc spec-url="/openapi.json"></redoc>
  <script src="https://cdn.jsdelivr.net/npm/redoc@2/bundles/redoc.standalone.js"></script>
</body>
</html>"""


def render_redoc() -> str:
    """Return the FJORD-themed ReDoc HTML."""
    return _REDOC_HTML.format(project=settings.PROJECT_NAME.upper())
