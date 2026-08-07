(function () {
  const script = document.currentScript;
  const target = document.getElementById("redoc-container");
  if (!script || !target) {
    return;
  }

  const openapiUrl = script.dataset.openapiUrl || "/openapi.json";
  const nonce = script.dataset.cspNonce || undefined;
  if (!window.Redoc || typeof window.Redoc.init !== "function") {
    target.textContent = "API reference failed to initialize.";
    return;
  }

  const styles = window.getComputedStyle(document.documentElement);
  const token = (name, fallback = "") =>
    styles.getPropertyValue(name).trim() || fallback;
  // Quiet HTTP verbs — same surface/ink as Swagger chips.
  const quietVerb = token("--color-surface");
  const fontSans = token("--font-sans", "Geist, system-ui, sans-serif");
  const fontMono = token(
    "--font-mono",
    "ui-monospace, SFMono-Regular, Menlo, monospace",
  );
  const options = {
    nativeScrollbars: true,
    sanitize: true,
    scrollYOffset: ".forjd-backend-topbar",
    theme: {
      spacing: {
        unit: 8,
        sectionHorizontal: 40,
        sectionVertical: 40,
      },
      colors: {
        primary: {
          main: token("--color-primary"),
          contrastText: token("--color-bg"),
        },
        success: {
          main: token("--color-success-ink"),
          contrastText: token("--color-bg"),
        },
        warning: {
          main: token("--color-warning-ink"),
          contrastText: token("--color-bg"),
        },
        error: {
          main: token("--color-error-ink"),
          contrastText: token("--color-bg"),
        },
        text: {
          primary: token("--color-text"),
          secondary: token("--color-text-secondary"),
        },
        border: {
          dark: token("--color-border"),
          light: token("--color-border"),
        },
        http: {
          get: quietVerb,
          post: quietVerb,
          put: quietVerb,
          options: quietVerb,
          patch: quietVerb,
          delete: quietVerb,
          basic: quietVerb,
          link: quietVerb,
          head: quietVerb,
        },
      },
      typography: {
        fontSize: "14px",
        lineHeight: "1.5em",
        fontWeightRegular: "400",
        fontWeightBold: "600",
        fontWeightLight: "300",
        fontFamily: fontSans,
        headings: {
          fontFamily: fontSans,
          fontWeight: "600",
          lineHeight: "1.35em",
        },
        code: {
          fontSize: "13px",
          fontFamily: fontMono,
          color: token("--color-success-ink"),
          backgroundColor: token("--color-surface"),
          wrap: true,
        },
        links: {
          color: token("--color-primary"),
          visited: token("--color-primary"),
          hover: token("--color-text"),
          textDecoration: "underline",
          hoverTextDecoration: "underline",
        },
      },
      sidebar: {
        width: "280px",
        backgroundColor: token("--color-surface"),
        textColor: token("--color-text-secondary"),
        activeTextColor: token("--color-text"),
        arrow: {
          color: token("--color-text-secondary"),
        },
      },
      rightPanel: {
        width: "40%",
        backgroundColor: token("--color-bg"),
        textColor: token("--color-text"),
        servers: {
          overlay: {
            backgroundColor: token("--color-surface"),
            textColor: token("--color-text"),
          },
          url: {
            backgroundColor: token("--color-surface"),
          },
        },
      },
      fab: {
        backgroundColor: token("--color-surface"),
        color: token("--color-text"),
      },
    },
  };
  if (nonce) {
    options.nonce = nonce;
  }

  window.Redoc.init(openapiUrl, options, target, (error) => {
    if (error) {
      target.textContent = "API reference failed to load.";
      return;
    }

    target.querySelectorAll('.api-content [id^="operation/"] h5').forEach((heading) => {
      heading.setAttribute("role", "heading");
      heading.setAttribute("aria-level", "3");
    });

    const normalizeMenus = () => {
      target
        .querySelectorAll('.menu-content ul, .menu-content [data-role="search:results"]')
        .forEach((container) => {
          if (container.querySelector(':scope > [role="menuitem"]')) {
            container.setAttribute("role", "menu");
          }
        });
    };
    normalizeMenus();

    const menu = target.querySelector(".menu-content");
    if (menu) {
      new MutationObserver(normalizeMenus).observe(menu, {
        childList: true,
        subtree: true,
      });
    }
  });
})();
