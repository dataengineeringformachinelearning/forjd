/**
 * Browser online/offline helpers — graceful degradation for the static landing.
 * Not a sync engine; partners keep their own offline/data plane.
 *
 * ADR: docs/adr/0009-graceful-offline-landing.md
 */

/** True when the browser reports a network path (may still fail DNS/TLS). */
export function isBrowserOnline(
  nav: Pick<Navigator, 'onLine'> | null | undefined = typeof navigator !== 'undefined'
    ? navigator
    : null,
): boolean {
  if (!nav || typeof nav.onLine !== 'boolean') {
    return true;
  }
  return nav.onLine;
}

export type OnlineStatusListener = (online: boolean) => void;

/**
 * Subscribe to `online` / `offline` window events. Returns an unsubscribe fn.
 * Does not emit the current status (call `isBrowserOnline()` for that).
 */
export function subscribeOnlineStatus(
  listener: OnlineStatusListener,
  target:
    Pick<Window, 'addEventListener' | 'removeEventListener'> | null | undefined = typeof window !==
  'undefined'
    ? window
    : null,
): () => void {
  if (!target) {
    return () => undefined;
  }
  const onOnline = (): void => listener(true);
  const onOffline = (): void => listener(false);
  target.addEventListener('online', onOnline);
  target.addEventListener('offline', onOffline);
  return () => {
    target.removeEventListener('online', onOnline);
    target.removeEventListener('offline', onOffline);
  };
}
