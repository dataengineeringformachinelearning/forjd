/**
 * Constrained-delivery detection — Save-Data + prefers-reduced-data.
 * High-end devices keep full atmosphere / idle analytics; metered paths skip extras.
 */

type NavigatorConnection = {
  readonly saveData?: boolean;
};

export type DeliveryWindow = Pick<Window, 'matchMedia'> & {
  readonly navigator: Navigator & { connection?: NavigatorConnection };
};

export function prefersConstrainedDelivery(target?: DeliveryWindow | null): boolean {
  const win = target ?? (typeof window !== 'undefined' ? (window as DeliveryWindow) : null);
  if (!win || typeof win.matchMedia !== 'function') {
    return false;
  }
  try {
    if (win.matchMedia('(prefers-reduced-data: reduce)').matches) {
      return true;
    }
  } catch {
    // matchMedia can throw in odd test environments
  }
  return Boolean(win.navigator?.connection?.saveData);
}
