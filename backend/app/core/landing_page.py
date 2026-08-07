"""Minimal brand splash served at ``GET /``.

Centered FORJD mark on warm ash. Human docs live on the community site.
"""

from __future__ import annotations

from app.core.config import settings

# --- Stable public suite hosts (splash chrome only) ---
_COMMUNITY_URL = "https://dataengineeringformachinelearning.com/"
_DOCS_URL = "https://dataengineeringformachinelearning.com/documentation"
_META_DESCRIPTION = "FORJD — secure streaming API for product integrations."

# --- Splash (deml-ui + forjd-backend.css) ---
_LANDING_HTML = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>{project} — Secure streaming API</title>
<meta name="description" content="{meta_description}" />
<meta name="robots" content="index, follow, max-image-preview:large" />
<link rel="canonical" href="https://backend.forjd.co/" />
<link rel="icon" type="image/svg+xml" href="/static/favicon.svg" />
<link rel="icon" type="image/png" sizes="96x96" href="/static/favicon-96x96.png" />
<link rel="apple-touch-icon" sizes="180x180" href="/static/apple-touch-icon.png" />
<meta name="theme-color" content="#35312D" />
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#D4CEC5" />
<meta name="color-scheme" content="light dark" />
<meta property="og:type" content="website" />
<meta property="og:url" content="https://backend.forjd.co/" />
<meta property="og:title" content="{project} — Secure streaming API" />
<meta property="og:description" content="{meta_description}" />
<meta property="og:image" content="https://backend.forjd.co/static/forjd.svg" />
<meta property="og:site_name" content="{project}" />
<meta property="og:locale" content="en_US" />
<meta name="twitter:card" content="summary" />
<meta name="twitter:title" content="{project} — Secure streaming API" />
<meta name="twitter:description" content="{meta_description}" />
<meta name="twitter:image" content="https://backend.forjd.co/static/forjd.svg" />
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebAPI",
  "name": "{project}",
  "description": "{meta_description}",
  "url": "https://backend.forjd.co/",
  "documentation": "{docs}"
}}
</script>
<link rel="stylesheet" href="/static/geist.css" />
<link rel="stylesheet" href="/static/deml-ui.css" />
<link rel="stylesheet" href="/static/forjd-backend.css" />
<script>
  (function () {{
    try {{
      var theme = localStorage.getItem('deml-theme');
      if (theme !== 'light' && theme !== 'dark') {{
        theme = window.matchMedia('(prefers-color-scheme: light)').matches
          ? 'light'
          : 'dark';
      }}
      document.documentElement.setAttribute('data-theme', theme);
    }} catch (e) {{}}
  }})();
</script>
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
<body class="forjd-backend-splash">
  <a class="skip-link" href="#main-content">Skip to main content</a>
  <main id="main-content" class="forjd-backend-shell" tabindex="-1">
    <a
      class="forjd-backend-logo"
      href="{community}"
      aria-label="{project} community home"
    >
      <img src="/static/forjd.svg" width="270" height="270" alt="{project}" />
    </a>
  </main>
</body>
</html>"""


def render_landing() -> str:
    """Return the centered brand-mark splash HTML."""
    return _LANDING_HTML.format(
        project=settings.PROJECT_NAME.upper(),
        meta_description=_META_DESCRIPTION,
        community=_COMMUNITY_URL,
        docs=_DOCS_URL,
    )
