"""Minimal FJORD splash served at ``GET /``.

Solid void canvas + centered mark. Interactive docs live on forjd.co
(Swagger ``/docs``, ReDoc ``/redoc``).
"""

# ruff: noqa: E501 -- compact CSS rules

from __future__ import annotations

from app.core.config import settings

# --- Minimal splash (FJORD tokens; no CDN) ---
_LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project}</title>
<meta name="description" content="FORJD secure streaming API." />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#0a0a0a" />
<style>
  :root {{
    color-scheme: dark;
    --fj-bg: #0a0a0a;
    --fj-primary: #00b4ff;
    --fj-focus: #00b4ff;
    --fj-border: #222222;
  }}
  *, *::before, *::after {{ box-sizing: border-box; }}
  html, body {{ margin: 0; min-height: 100%; background: var(--fj-bg); }}
  body {{
    background:
      radial-gradient(90% 55% at 50% 35%, color-mix(in srgb, var(--fj-primary) 10%, transparent), transparent 60%),
      var(--fj-bg);
  }}
  a:focus-visible {{ outline: 2px solid var(--fj-focus); outline-offset: 4px; }}
  .splash {{
    min-height: 100dvh; display: grid; place-items: center; padding: 1.5rem;
  }}
  .splash__logo {{
    display: block; width: min(8rem, 38vw); height: auto; border: 0;
    filter: drop-shadow(0 0 28px color-mix(in srgb, var(--fj-primary) 30%, transparent));
    transition: transform 220ms cubic-bezier(0.22, 1, 0.36, 1), filter 220ms ease;
  }}
  .splash__logo:hover {{
    transform: translateY(-2px);
    filter: drop-shadow(0 0 36px color-mix(in srgb, var(--fj-primary) 42%, transparent));
  }}
  .splash__logo img {{
    display: block; width: 100%; height: auto;
  }}
  @media (prefers-reduced-motion: reduce) {{
    .splash__logo {{ transition: none; }}
    .splash__logo:hover {{ transform: none; }}
  }}
</style>
</head>
<body>
  <main class="splash">
    <a class="splash__logo" href="https://forjd.co/" aria-label="{project} product site">
      <img src="/static/forjd.svg" width="270" height="270" alt="{project}" />
    </a>
  </main>
</body>
</html>"""


def render_landing() -> str:
    """Return the minimal FJORD splash HTML."""
    return _LANDING_HTML.format(project=settings.PROJECT_NAME.upper())
