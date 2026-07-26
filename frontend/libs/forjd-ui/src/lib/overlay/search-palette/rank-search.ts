/**
 * Fast ranked matching for the suite command palette.
 * Prefer title prefix / exact hits over keyword / snippet noise.
 */

import type { FjSearchPaletteItem } from './search-palette.types';

const MAX_RESULTS = 48;

/** Score one item against a query (0 = no match). */
export function scoreSearchItem(item: FjSearchPaletteItem, query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) {
    return 0;
  }
  const title = item.title.toLowerCase();
  if (title === q) {
    return 100;
  }
  if (title.startsWith(q)) {
    return 80;
  }
  if (title.includes(q)) {
    return 60;
  }

  const keywords = (item.keywords ?? []).join(' ').toLowerCase();
  if (keywords.includes(q)) {
    return 45;
  }

  const tokens = q.split(/\s+/).filter(Boolean);
  if (tokens.length > 1) {
    let hits = 0;
    for (const token of tokens) {
      if (
        title.includes(token) ||
        keywords.includes(token) ||
        (item.snippet ?? '').toLowerCase().includes(token)
      ) {
        hits += 1;
      }
    }
    if (hits === tokens.length) {
      return 50;
    }
    if (hits > 0) {
      return 12 * hits;
    }
  }

  const snippet = (item.snippet ?? '').toLowerCase();
  if (snippet.includes(q)) {
    return 25;
  }
  const group = (item.group ?? '').toLowerCase();
  if (group.includes(q)) {
    return 15;
  }
  const href = item.href.toLowerCase();
  if (href.includes(q)) {
    return 10;
  }
  return 0;
}

/** Filter + rank items; empty query returns the curated list unchanged (caller may inject recents). */
export function rankSearchItems(
  items: readonly FjSearchPaletteItem[],
  query: string,
  options?: { readonly limit?: number },
): FjSearchPaletteItem[] {
  const limit = options?.limit ?? MAX_RESULTS;
  const q = query.trim();
  if (!q) {
    return items.slice(0, Math.max(0, limit));
  }
  return items
    .map((item) => ({ item, score: scoreSearchItem(item, q) }))
    .filter((row) => row.score > 0)
    .sort((a, b) => b.score - a.score || a.item.title.localeCompare(b.item.title))
    .slice(0, Math.max(0, limit))
    .map((row) => row.item);
}
