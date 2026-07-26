/** Local Angular env — see config/forjd.catalog.yaml / docs/CONFIGURATION.md */
export const environment = {
  production: false,
  apiBaseUrl: 'http://127.0.0.1:8000',
  // Leave empty locally unless debugging observability integrations.
  sentryDsn: '',
  rollbarAccessToken: '',
};
