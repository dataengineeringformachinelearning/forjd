/**
 * Pure window math for fixed-height virtual lists (forjd-ui / suite adapter).
 * Flat index lists via `indicesForWindow` — ADR-0010.
 */

export type FjVirtualWindowInput = {
  scrollTop: number;
  viewportHeight: number;
  itemCount: number;
  itemHeight: number;
  overscan?: number;
};

export type FjVirtualWindow = {
  start: number;
  end: number;
  offsetY: number;
  totalHeight: number;
  visibleCount: number;
};

export function computeVirtualWindow(input: FjVirtualWindowInput): FjVirtualWindow {
  const itemHeight = Math.max(1, input.itemHeight);
  const itemCount = Math.max(0, Math.floor(input.itemCount));
  const viewportHeight = Math.max(0, input.viewportHeight);
  const scrollTop = Math.max(0, input.scrollTop);
  const overscan = Math.max(0, Math.floor(input.overscan ?? 4));
  const totalHeight = itemCount * itemHeight;

  if (itemCount === 0) {
    return { start: 0, end: 0, offsetY: 0, totalHeight: 0, visibleCount: 0 };
  }

  const rawStart = Math.floor(scrollTop / itemHeight);
  const visible = Math.ceil(viewportHeight / itemHeight) + 1;
  let start = Math.max(0, rawStart - overscan);
  let end = Math.min(itemCount, rawStart + visible + overscan);
  // Past the end (overscroll / stale scrollTop): pin the window to the tail.
  if (start >= itemCount) {
    start = Math.max(0, itemCount - visible - overscan);
    end = itemCount;
  } else if (start > end) {
    start = end;
  }

  return {
    start,
    end,
    offsetY: start * itemHeight,
    totalHeight,
    visibleCount: Math.max(0, end - start),
  };
}

/** Flat index list for a window — prefer over `{ item, index }[]` wrappers. */
export function indicesForWindow(start: number, end: number): number[] {
  if (end <= start) {
    return [];
  }
  const out = new Array<number>(end - start);
  for (let i = 0; i < out.length; i++) {
    out[i] = start + i;
  }
  return out;
}
