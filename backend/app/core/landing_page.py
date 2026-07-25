"""Minimal suite splash served at ``GET /``.

Centered logo only. Interactive docs live on forjd.co
(Swagger ``/docs``, ReDoc ``/redoc``).
"""

from __future__ import annotations

from app.core.config import settings

# --- Minimal splash (suite-backend.css; no inline chrome) ---
_LANDING_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{project}</title>
<meta name="description" content="FORJD secure streaming API." />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#0a0a0a" />
<link rel="stylesheet" href="/static/suite-tokens.css" />
<link rel="stylesheet" href="/static/suite-components.css" />
<link rel="stylesheet" href="/static/suite-backend.css" />
<!-- First-party page analytics for backend.forjd.co HTML shell -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2VGSZ68733"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){{ dataLayer.push(arguments); }}
  gtag('js', new Date());
  gtag('config', 'G-2VGSZ68733', {{ cookie_flags: 'SameSite=None;Secure;Partitioned' }});
</script>
<script type="text/javascript">
  (function(c,l,a,r,i,t,y){{
    c[a]=c[a]||function(){{(c[a].q=c[a].q||[]).push(arguments)}};
    t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
    y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);
  }})(window, document, "clarity", "script", "xddv4klojn");
</script>
</head>
<body class="suite-backend-splash backend-splash">
  <main class="suite-backend-shell backend-splash-shell">
    <a
      class="suite-backend-logo backend-splash-logo"
      href="https://forjd.co/"
      aria-label="{project} product site"
    >
      <img src="/static/forjd.svg" width="270" height="270" alt="{project}" />
    </a>
  </main>
</body>
</html>"""


def render_landing() -> str:
    """Return the minimal suite splash HTML."""
    return _LANDING_HTML.format(project=settings.PROJECT_NAME.upper())
