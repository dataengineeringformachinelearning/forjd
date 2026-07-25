/** Production / Vercel — UI at https://forjd.co */
export const environment = {
  production: true,
  apiBaseUrl: 'https://backend.forjd.co',
  // Client DSN / post_client_item tokens are public by design.
  sentryDsn:
    'https://e451eccd44f57a666f280fca6306e4a8@o4511437520044032.ingest.us.sentry.io/4511793590566912', // pragma: allowlist secret
  rollbarAccessToken: 'c7d98f5f14df458fb05a02c4414af266', // pragma: allowlist secret
};
