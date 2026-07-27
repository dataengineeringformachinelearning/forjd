(function () {
  const script = document.currentScript;
  const target = document.getElementById('redoc-container');
  if (!script || !target) {
    return;
  }

  const openapiUrl = script.dataset.openapiUrl || '/openapi.json';
  const nonce = script.dataset.cspNonce || undefined;
  if (!window.Redoc || typeof window.Redoc.init !== 'function') {
    target.textContent = 'API reference failed to initialize.';
    return;
  }

  const styles = window.getComputedStyle(document.documentElement);
  const token = (name) => styles.getPropertyValue(name).trim();
  const options = {
    nativeScrollbars: true,
    sanitize: true,
    scrollYOffset: '.suite-backend-topbar',
    theme: {
      spacing: {
        unit: 8,
        sectionHorizontal: 40,
        sectionVertical: 40,
      },
      colors: {
        primary: {
          main: token('--suite-primary-strong'),
          contrastText: token('--suite-bg'),
        },
        success: {
          main: token('--suite-success-text'),
          contrastText: token('--suite-bg'),
        },
        warning: {
          main: token('--suite-warning-text'),
          contrastText: token('--suite-bg'),
        },
        error: {
          main: token('--suite-danger-text'),
          contrastText: token('--suite-bg'),
        },
        text: {
          primary: token('--suite-ink'),
          secondary: token('--suite-ink-muted'),
        },
        border: {
          dark: token('--suite-border-strong'),
          light: token('--suite-border'),
        },
        http: {
          get: token('--suite-success-text'),
          post: token('--suite-primary-strong'),
          put: token('--suite-gold-text'),
          options: token('--suite-ink-muted'),
          patch: token('--suite-warning-text'),
          delete: token('--suite-danger-text'),
          basic: token('--suite-ink-muted'),
          link: token('--suite-primary-strong'),
          head: token('--suite-ink-muted'),
        },
      },
      typography: {
        fontSize: '14px',
        lineHeight: '1.5em',
        fontWeightRegular: '400',
        fontWeightBold: '600',
        fontWeightLight: '300',
        fontFamily: token('--suite-font-sans'),
        headings: {
          fontFamily: token('--suite-font-sans'),
          fontWeight: '600',
          lineHeight: '1.35em',
        },
        code: {
          fontSize: '13px',
          fontFamily: token('--suite-font-mono'),
          color: token('--suite-success-text'),
          backgroundColor: token('--suite-surface-2'),
          wrap: true,
        },
        links: {
          color: token('--suite-primary-strong'),
          visited: token('--suite-primary-strong'),
          hover: token('--suite-ink'),
          textDecoration: 'underline',
          hoverTextDecoration: 'underline',
        },
      },
      sidebar: {
        width: '280px',
        backgroundColor: token('--suite-surface'),
        textColor: token('--suite-ink-muted'),
        activeTextColor: token('--suite-ink'),
        arrow: {
          color: token('--suite-ink-muted'),
        },
      },
      rightPanel: {
        width: '40%',
        backgroundColor: token('--suite-bg-subtle'),
        textColor: token('--suite-ink'),
        servers: {
          overlay: {
            backgroundColor: token('--suite-surface'),
            textColor: token('--suite-ink'),
          },
          url: {
            backgroundColor: token('--suite-surface-2'),
          },
        },
      },
      fab: {
        backgroundColor: token('--suite-surface-2'),
        color: token('--suite-ink'),
      },
    },
  };
  if (nonce) {
    options.nonce = nonce;
  }

  window.Redoc.init(openapiUrl, options, target, (error) => {
    if (error) {
      target.textContent = 'API reference failed to load.';
      return;
    }

    // ReDoc 2 emits operation subheadings as h5 elements directly below h2
    // operation headings. Preserve its visual style while exposing the actual
    // document hierarchy to assistive technology.
    target.querySelectorAll('.api-content [id^="operation/"] h5').forEach((heading) => {
      heading.setAttribute('role', 'heading');
      heading.setAttribute('aria-level', '3');
    });

    const normalizeMenus = () => {
      target
        .querySelectorAll('.menu-content ul, .menu-content [data-role="search:results"]')
        .forEach((container) => {
          if (container.querySelector(':scope > [role="menuitem"]')) {
            container.setAttribute('role', 'menu');
          }
        });
    };
    normalizeMenus();

    const menu = target.querySelector('.menu-content');
    if (menu) {
      new MutationObserver(normalizeMenus).observe(menu, {
        childList: true,
        subtree: true,
      });
    }
  });
})();
