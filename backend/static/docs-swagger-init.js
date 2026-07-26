/* Swagger UI boot — self-hosted; no inline script in /docs HTML. */
(function () {
  var openapiUrl =
    (document.currentScript && document.currentScript.getAttribute('data-openapi-url')) ||
    '/openapi.json';
  if (typeof SwaggerUIBundle === 'undefined') {
    console.error('SwaggerUIBundle missing — check /static/vendor/swagger-ui-dist/');
    return;
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
  });
})();
