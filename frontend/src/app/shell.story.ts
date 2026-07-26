/**
 * App-shell failure copy — same partner voice as the landing ready story.
 * Used by error boundary + GlobalErrorHandler toast (not ops jargon).
 */

export const SHELL_STORY = {
  errorBoundary: {
    title: 'This page could not load',
    description: 'FORJD hit an unexpected error. Retry this section, or refresh if it continues.',
  },
  unexpectedToast: {
    title: 'Something interrupted the page',
    description: 'Try again, or refresh if it continues.',
  },
} as const;
