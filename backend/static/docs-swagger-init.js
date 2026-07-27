/* Swagger UI boot — self-hosted; no inline script in /docs HTML. */
(function () {
  var openapiUrl =
    (document.currentScript && document.currentScript.getAttribute('data-openapi-url')) ||
    '/openapi.json';
  if (typeof SwaggerUIBundle === 'undefined') {
    console.error('SwaggerUIBundle missing — check /static/vendor/swagger-ui-dist/');
    return;
  }

  var observer;
  function normalizeSwaggerAccessibility() {
    var root = document.getElementById('swagger-ui');
    if (!root) {
      return;
    }

    root.querySelectorAll('.opblock-summary-control').forEach(function (control) {
      var method = control.querySelector('.opblock-summary-method');
      var path = control.querySelector('.opblock-summary-path');
      var description = control.querySelector('.opblock-summary-description');
      control.setAttribute(
        'aria-label',
        [method, path, description]
          .map(function (element) {
            return element && element.textContent ? element.textContent.trim() : '';
          })
          .filter(Boolean)
          .join(' — '),
      );

      control.querySelectorAll('a[href]').forEach(function (link) {
        link.removeAttribute('href');
        link.setAttribute('role', 'presentation');
        link.setAttribute('tabindex', '-1');
      });
    });

    root.querySelectorAll('.copy-to-clipboard button').forEach(function (button) {
      if (!button.getAttribute('aria-label')) {
        button.setAttribute(
          'aria-label',
          button.closest('.curl-command') ? 'Copy curl command' : 'Copy response body',
        );
      }
    });

    root.querySelectorAll('pre.microlight').forEach(function (sample) {
      sample.setAttribute('tabindex', '0');
      sample.setAttribute('role', 'group');
      sample.setAttribute('aria-label', 'Scrollable code sample');
    });

    if (!observer) {
      observer = new MutationObserver(normalizeSwaggerAccessibility);
      observer.observe(root, { childList: true, subtree: true });
    }
  }

  window.ui = SwaggerUIBundle({
    url: openapiUrl,
    dom_id: '#swagger-ui',
    presets: [SwaggerUIBundle.presets.apis],
    layout: 'BaseLayout',
    deepLinking: true,
    displayRequestDuration: true,
    defaultModelsExpandDepth: 0,
    persistAuthorization: false,
    onComplete: normalizeSwaggerAccessibility,
  });
})();
