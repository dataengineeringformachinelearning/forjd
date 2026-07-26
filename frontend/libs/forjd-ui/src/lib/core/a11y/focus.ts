/**
 * Suite focus helpers (forjd-ui adapter copy — keep API aligned with viking-ui/core/focus).
 */

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  "input:not([disabled]):not([type='hidden'])",
  'select:not([disabled])',
  'textarea:not([disabled])',
  'iframe',
  'object',
  'embed',
  "[contenteditable]:not([contenteditable='false'])",
  '[tabindex]:not([tabindex="-1"])',
].join(',');

export function isFocusable(el: Element | null | undefined): el is HTMLElement {
  if (!(el instanceof HTMLElement)) return false;
  if (el.hasAttribute('disabled') || el.getAttribute('aria-disabled') === 'true') {
    return false;
  }
  if (el.closest("[inert], [hidden], [aria-hidden='true']")) return false;
  const style = globalThis.getComputedStyle?.(el);
  if (style && (style.visibility === 'hidden' || style.display === 'none')) {
    return false;
  }
  return el.matches(FOCUSABLE_SELECTOR);
}

export function getFocusableElements(root: ParentNode): HTMLElement[] {
  const nodes = Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
  return nodes.filter((el) => isFocusable(el));
}

export function focusFirst(
  root: HTMLElement,
  options: FocusOptions = { preventScroll: true },
): HTMLElement | null {
  const candidates = getFocusableElements(root);
  const target = candidates[0] ?? (isFocusable(root) ? root : null);
  target?.focus(options);
  return target;
}

export function captureReturnFocus(
  active: Element | null = typeof document !== 'undefined' ? document.activeElement : null,
): HTMLElement | null {
  return active instanceof HTMLElement ? active : null;
}

export function restoreFocus(
  el: HTMLElement | null | undefined,
  options: FocusOptions = { preventScroll: true },
): void {
  if (!el || !el.isConnected) return;
  try {
    el.focus(options);
  } catch {
    /* ignore */
  }
}

/**
 * Roving tabindex index math for tablists / menubars.
 * Returns the next index, or null if the key is not a navigation key.
 */
export function nextRovingIndex(
  key: string,
  currentIndex: number,
  length: number,
  options: { vertical?: boolean; wrap?: boolean } = {},
): number | null {
  if (length <= 0) return null;
  const wrap = options.wrap !== false;
  const vertical = options.vertical === true;
  let next = currentIndex;

  switch (key) {
    case 'ArrowRight':
      if (vertical) return null;
      next = currentIndex + 1;
      break;
    case 'ArrowLeft':
      if (vertical) return null;
      next = currentIndex - 1;
      break;
    case 'ArrowDown':
      if (!vertical) return null;
      next = currentIndex + 1;
      break;
    case 'ArrowUp':
      if (!vertical) return null;
      next = currentIndex - 1;
      break;
    case 'Home':
      return 0;
    case 'End':
      return length - 1;
    default:
      return null;
  }

  if (wrap) {
    return (next + length) % length;
  }
  return Math.max(0, Math.min(length - 1, next));
}

/** Both-axis arrows (FORJD tabs / grids). */
export function nextRovingIndexBothAxes(
  key: string,
  currentIndex: number,
  length: number,
): number | null {
  if (length <= 0) return null;
  switch (key) {
    case 'ArrowRight':
    case 'ArrowDown':
      return (currentIndex + 1) % length;
    case 'ArrowLeft':
    case 'ArrowUp':
      return (currentIndex - 1 + length) % length;
    case 'Home':
      return 0;
    case 'End':
      return length - 1;
    default:
      return null;
  }
}

/** Horizontal menubar / nav list. */
export function nextRovingIndexHorizontal(
  key: string,
  currentIndex: number,
  length: number,
): number | null {
  return nextRovingIndex(key, currentIndex, length, { vertical: false });
}

/** Trap Tab / Shift+Tab inside an overlay root (WCAG focus retention). */
export function trapTabKey(event: KeyboardEvent, root: HTMLElement): void {
  if (event.key !== 'Tab') return;
  const items = getFocusableElements(root);
  if (items.length === 0) {
    event.preventDefault();
    root.focus({ preventScroll: true });
    return;
  }
  const first = items[0];
  const last = items[items.length - 1];
  const active = typeof document !== 'undefined' ? document.activeElement : null;
  if (event.shiftKey) {
    if (active === first || !root.contains(active)) {
      event.preventDefault();
      last.focus({ preventScroll: true });
    }
    return;
  }
  if (active === last || !root.contains(active)) {
    event.preventDefault();
    first.focus({ preventScroll: true });
  }
}
