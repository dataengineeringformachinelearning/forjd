"""FJORD-themed public landing page served at ``GET /``.

Self-contained HTML + CSS using FJORD tokens (aligned with forjd-ui).
Swagger stays at ``/docs``; this page is the intentional API entry surface.
"""

# ruff: noqa: E501 -- CSS rules read better as compact one-liners.

from __future__ import annotations

from app.core.config import settings

# --- Landing shell (FJORD tokens; no CDN required for first paint) ---
_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project} — Secure streaming API</title>
<meta name="description" content="FORJD universal secure streaming engine — sealed E2EE ingest, YAML workflows, durable projections, and replay/DLQ." />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#0a0a0a" />
<style>
  :root {{
    color-scheme: dark;
    --fj-bg: #0a0a0a; --fj-surface: #111111; --fj-surface-2: #1a1a1a;
    --fj-border: #222222; --fj-primary: #00b4ff; --fj-primary-hover: #33c3ff;
    --fj-focus: #00b4ff; --fj-success: #00e6a6; --fj-warning: #ff9500; --fj-danger: #ff2d55;
    --fj-text: #f0f0f0; --fj-text-muted: #888888; --fj-text-on-primary: #0a0a0a;
    --fj-sans: 'IBM Plex Sans', 'Segoe UI', system-ui, sans-serif;
    --fj-mono: 'IBM Plex Mono', ui-monospace, monospace;
    --fj-radius: 4px;
    --fj-space-2: 0.5rem; --fj-space-3: 0.75rem; --fj-space-4: 1rem;
    --fj-space-6: 1.5rem; --fj-space-8: 2rem;
  }}
  *, *::before, *::after {{ box-sizing: border-box; }}
  html, body {{ margin: 0; min-height: 100%; background: var(--fj-bg); color: var(--fj-text); font-family: var(--fj-sans); }}
  a {{ color: inherit; }}
  a:focus-visible, button:focus-visible {{ outline: 2px solid var(--fj-focus); outline-offset: 2px; }}

  .skip {{ position: absolute; left: -9999px; top: 0; background: var(--fj-surface); color: var(--fj-text); padding: var(--fj-space-2) var(--fj-space-3); z-index: 10; }}
  .skip:focus {{ left: var(--fj-space-3); top: var(--fj-space-3); }}

  .shell {{
    min-height: 100dvh; display: flex; flex-direction: column;
    max-width: 56rem; margin: 0 auto; padding: var(--fj-space-6);
  }}
  @media (min-width: 768px) {{
    .shell {{ padding: var(--fj-space-8) var(--fj-space-6); justify-content: center; gap: var(--fj-space-8); }}
  }}

  .topbar {{
    display: flex; align-items: center; justify-content: space-between; gap: var(--fj-space-4);
    padding-bottom: var(--fj-space-4); border-bottom: 1px solid var(--fj-border); margin-bottom: var(--fj-space-6);
  }}
  .brand {{
    font-family: var(--fj-mono); letter-spacing: 0.12em; text-transform: uppercase;
    font-size: 0.8rem; color: var(--fj-primary); font-weight: 600; text-decoration: none;
  }}
  .topnav {{ display: flex; flex-wrap: wrap; gap: var(--fj-space-3) var(--fj-space-4); }}
  .topnav a {{
    color: var(--fj-text-muted); font-size: 0.8125rem; font-family: var(--fj-mono); text-decoration: none;
  }}
  .topnav a:hover {{ color: var(--fj-primary); }}

  .hero {{ display: flex; flex-direction: column; gap: var(--fj-space-4); flex: 1; justify-content: center; }}
  .eyebrow {{
    margin: 0; font-family: var(--fj-mono); font-size: 0.75rem; letter-spacing: 0.1em;
    text-transform: uppercase; color: var(--fj-text-muted);
  }}
  .headline {{
    margin: 0; font-size: clamp(1.75rem, 4vw, 2.25rem); line-height: 1.15;
    letter-spacing: -0.02em; font-weight: 600; max-width: 20ch;
  }}
  .lede {{
    margin: 0; max-width: 42rem; color: var(--fj-text-muted);
    font-size: 1rem; line-height: 1.5;
  }}

  .chips {{
    display: flex; flex-wrap: wrap; gap: var(--fj-space-2); margin-top: var(--fj-space-2);
  }}
  .chip {{
    display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.35rem 0.7rem; border: 1px solid var(--fj-border); border-radius: 999px;
    background: var(--fj-surface); color: var(--fj-text-muted);
    font-family: var(--fj-mono); font-size: 0.75rem; text-decoration: none;
  }}
  .chip:hover {{ border-color: var(--fj-primary); color: var(--fj-primary); }}
  .chip__dot {{
    width: 0.45rem; height: 0.45rem; border-radius: 50%; background: var(--fj-text-muted);
  }}
  .chip[data-state="ok"] .chip__dot {{ background: var(--fj-success); }}
  .chip[data-state="warn"] .chip__dot {{ background: var(--fj-warning); }}
  .chip[data-state="down"] .chip__dot {{ background: var(--fj-danger); }}

  .actions {{ display: flex; flex-wrap: wrap; gap: var(--fj-space-3); margin-top: var(--fj-space-2); }}
  .btn {{
    display: inline-flex; align-items: center; justify-content: center;
    min-height: 2.75rem; padding: var(--fj-space-2) var(--fj-space-4);
    border-radius: var(--fj-radius); font-size: 0.875rem; font-weight: 600;
    text-decoration: none; border: 1px solid transparent;
  }}
  .btn-primary {{ background: var(--fj-primary); color: var(--fj-text-on-primary); }}
  .btn-primary:hover {{ background: var(--fj-primary-hover); }}
  .btn-ghost {{
    background: transparent; color: var(--fj-text); border-color: var(--fj-border);
  }}
  .btn-ghost:hover {{ border-color: var(--fj-primary); color: var(--fj-primary); }}

  .grid {{
    display: grid; grid-template-columns: 1fr; gap: var(--fj-space-3); margin-top: var(--fj-space-6);
  }}
  @media (min-width: 600px) {{
    .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  }}
  .card {{
    background: var(--fj-surface); border: 1px solid var(--fj-border); border-radius: var(--fj-radius);
    padding: var(--fj-space-4); min-height: 100%;
  }}
  .card h2 {{
    margin: 0 0 var(--fj-space-3); font-family: var(--fj-mono); font-size: 0.75rem;
    letter-spacing: 0.08em; text-transform: uppercase; color: var(--fj-primary); font-weight: 600;
  }}
  .card p {{ margin: 0; color: var(--fj-text-muted); font-size: 0.875rem; line-height: 1.5; }}

  .meta {{
    display: grid; grid-template-columns: 1fr; gap: var(--fj-space-3);
    margin-top: auto; padding-top: var(--fj-space-6); border-top: 1px solid var(--fj-border);
    font-size: 0.8125rem;
  }}
  @media (min-width: 600px) {{
    .meta {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
  }}
  .meta span {{ display: block; color: var(--fj-text-muted); font-family: var(--fj-mono); margin-bottom: 0.2rem; }}
  .meta code {{ color: var(--fj-success); font-family: var(--fj-mono); }}

  @media (prefers-reduced-motion: reduce) {{
    .chip__dot {{ transition: none; }}
  }}
</style>
</head>
<body>
  <a class="skip" href="#main">Skip to main content</a>
  <div class="shell">
    <header class="topbar">
      <a class="brand" href="/">{project}</a>
      <nav class="topnav" aria-label="API links">
        <a href="/docs">docs</a>
        <a href="/redoc">redoc</a>
        <a href="/openapi.json">openapi</a>
        <a href="/health">health</a>
        <a href="/ready">ready</a>
        <a href="https://forjd.co">product</a>
      </nav>
    </header>

    <main id="main" class="hero">
      <p class="eyebrow">Secure streaming control plane</p>
      <h1 class="headline">Universal secure streaming engine</h1>
      <p class="lede">
        Sealed end-to-end encrypted ingest, configurable YAML workflows, durable projections,
        and replay/DLQ — driven by a Rust hot-path and FastAPI edge.
      </p>

      <div class="chips" aria-label="Service probes">
        <a class="chip" id="chip-health" href="/health" data-state="pending">
          <span class="chip__dot" aria-hidden="true"></span>
          <span>health</span>
        </a>
        <a class="chip" id="chip-ready" href="/ready" data-state="pending">
          <span class="chip__dot" aria-hidden="true"></span>
          <span>ready</span>
        </a>
        <a class="chip" href="/docs">
          <span class="chip__dot" aria-hidden="true"></span>
          <span>swagger</span>
        </a>
        <a class="chip" href="/openapi.json">
          <span class="chip__dot" aria-hidden="true"></span>
          <span>openapi</span>
        </a>
        <a class="chip" href="/api/v1/addons">
          <span class="chip__dot" aria-hidden="true"></span>
          <span>addons</span>
        </a>
      </div>

      <div class="actions">
        <a class="btn btn-primary" href="/docs">API docs</a>
        <a class="btn btn-ghost" href="/redoc">ReDoc</a>
        <a class="btn btn-ghost" href="https://forjd.co">Product site</a>
      </div>

      <section class="grid" aria-label="Capabilities">
        <article class="card">
          <h2>Sealed ingest</h2>
          <p>Ciphertext-only E2EE envelopes. Partners keep plaintext; FORJD stores and routes sealed events.</p>
        </article>
        <article class="card">
          <h2>Workflows</h2>
          <p>YAML-configured pipelines with durable projections, replay, and DLQ for recoverable failure paths.</p>
        </article>
        <article class="card">
          <h2>Engine</h2>
          <p>Rust hot-path for Arrow/Parquet processing; FastAPI for auth, tenancy, and partner-facing APIs.</p>
        </article>
      </section>
    </main>

    <footer class="meta">
      <div>
        <span>service</span>
        <code>{project} · v{version}</code>
      </div>
      <div>
        <span>edge</span>
        <code>backend.forjd.co</code>
      </div>
      <div>
        <span>stack</span>
        <code>rust · fastapi · postgres</code>
      </div>
    </footer>
  </div>
  <script>
    (function () {{
      function setChip(id, state, label) {{
        var el = document.getElementById(id);
        if (!el) return;
        el.setAttribute('data-state', state);
        var text = el.querySelector('span:last-child');
        if (text && label) text.textContent = label;
      }}
      function probe(path, id, okLabel) {{
        fetch(path, {{ credentials: 'omit' }})
          .then(function (r) {{
            if (r.ok) setChip(id, 'ok', okLabel);
            else if (r.status === 503) setChip(id, 'warn', id.replace('chip-', '') + ' · degraded');
            else setChip(id, 'down', id.replace('chip-', '') + ' · ' + r.status);
          }})
          .catch(function () {{ setChip(id, 'down', id.replace('chip-', '') + ' · unreachable'); }});
      }}
      probe('/health', 'chip-health', 'health · ok');
      probe('/ready', 'chip-ready', 'ready · ok');
    }})();
  </script>
</body>
</html>"""


def render_landing() -> str:
    """Return the FJORD-themed API landing HTML."""
    return _LANDING_HTML.format(
        project=settings.PROJECT_NAME.upper(),
        version=settings.PROJECT_VERSION,
    )
