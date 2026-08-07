"""Community-style splash served at ``GET /``.

Simple deml-ui hero with the FORJD mark. Human docs live on the community site.
"""

from __future__ import annotations

from app.core.config import settings

# --- Stable public suite hosts (splash chrome only) ---
_COMMUNITY_URL = "https://dataengineeringformachinelearning.com/"
_BOOK_URL = "https://dataengineeringformachinelearning.com/book"
_WHITEPAPER_URL = "https://dataengineeringformachinelearning.com/whitepaper"
_DOCS_URL = "https://dataengineeringformachinelearning.com/documentation"
_BLOG_URL = "https://dataengineeringformachinelearning.com/blog"
_COMPLIANCE_URL = "https://dataengineeringformachinelearning.com/compliance"
_PRIVACY_URL = "https://dataengineeringformachinelearning.com/privacy/"
_TERMS_URL = "https://dataengineeringformachinelearning.com/terms/"
_DEML_URL = "https://deml.app/"
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
  <header class="forjd-backend-nav" aria-label="Site">
    <a class="forjd-backend-nav__brand" href="/" aria-label="{project} home">
      <img src="/static/forjd.svg" width="28" height="28" alt="" />
      <span>{project}</span>
    </a>
    <nav class="forjd-backend-nav__links" aria-label="Primary">
      <a href="{book}">Book</a>
      <a href="{whitepaper}">Whitepaper</a>
      <a href="{docs}">Docs</a>
      <a href="{blog}">Blog</a>
      <a href="{compliance}">Compliance</a>
      <a href="{community}">Community</a>
    </nav>
    <div class="forjd-backend-nav__actions">
      <a class="button button--primary button--pill" href="{deml}">DEML</a>
    </div>
  </header>
  <main id="main-content" class="forjd-backend-shell" tabindex="-1">
    <div class="page">
      <section class="banner banner--hero" data-variant="hero" aria-labelledby="main-title">
        <a class="forjd-backend-logo" href="/" aria-label="{project} home">
          <img src="/static/forjd.svg" width="120" height="120" alt="{project}" />
        </a>
        <p class="preheader">{project}</p>
        <h1 class="banner-heading" id="main-title">Secure streaming for product integrations.</h1>
        <p class="lede">
          Send events, run workflows, and read analytics through the FORJD API.
        </p>
        <div class="banner-actions">
          <div class="button-group" data-layout="row" role="group" aria-label="Primary actions">
            <a class="button button--primary button--pill" href="{docs}">Documentation</a>
            <a class="button button--secondary button--pill" href="{community}">Community</a>
          </div>
        </div>
      </section>
    </div>
  </main>
  <footer class="site-footer">
    <div class="site-footer__inner">
      <nav class="site-footer__directory" aria-label="Footer">
        <div class="site-footer__group">
          <p class="site-footer__heading">Resources</p>
          <ul class="site-footer__list">
            <li><a href="{book}">Book</a></li>
            <li><a href="{whitepaper}">Whitepaper</a></li>
            <li><a href="{docs}">Docs</a></li>
            <li><a href="{blog}">Blog</a></li>
            <li><a href="{deml}">DEML</a></li>
            <li><a href="{community}">Community</a></li>
          </ul>
        </div>
        <div class="site-footer__group">
          <p class="site-footer__heading">Legal</p>
          <ul class="site-footer__list">
            <li><a href="{compliance}">Compliance</a></li>
            <li><a href="{privacy}">Privacy</a></li>
            <li><a href="{terms}">Terms</a></li>
            <li><a href="/health">Health</a></li>
          </ul>
        </div>
      </nav>
    </div>
  </footer>
</body>
</html>"""


def render_landing() -> str:
    """Return the community-style deml-ui splash HTML."""
    return _LANDING_HTML.format(
        project=settings.PROJECT_NAME.upper(),
        meta_description=_META_DESCRIPTION,
        community=_COMMUNITY_URL,
        book=_BOOK_URL,
        whitepaper=_WHITEPAPER_URL,
        docs=_DOCS_URL,
        blog=_BLOG_URL,
        compliance=_COMPLIANCE_URL,
        privacy=_PRIVACY_URL,
        terms=_TERMS_URL,
        deml=_DEML_URL,
    )
