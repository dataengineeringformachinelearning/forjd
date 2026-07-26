/**
 * Recent search persistence for the suite command palette (localStorage).
 * Stores query strings and recently opened destinations — never secrets.
 */

import type { FjSearchPaletteItem } from './search-palette.types';

export const DEFAULT_RECENT_STORAGE_KEY = 'fj-search-recent-v1';
export const DEFAULT_RECENT_LIMIT = 8;

export type FjRecentSearch = {
  readonly query: string;
  readonly title?: string;
  readonly href?: string;
  readonly at: number;
};

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function safeStorage(): StorageLike | null {
  try {
    if (typeof globalThis.localStorage === 'undefined') {
      return null;
    }
    return globalThis.localStorage;
  } catch {
    return null;
  }
}

function normalizeQuery(query: string): string {
  return query.trim().replace(/\s+/g, ' ').slice(0, 120);
}

/** Read recent entries (newest first). */
export function readRecentSearches(
  storageKey: string = DEFAULT_RECENT_STORAGE_KEY,
  options?: { readonly limit?: number },
): FjRecentSearch[] {
  const limit = options?.limit ?? DEFAULT_RECENT_LIMIT;
  const storage = safeStorage();
  if (!storage) {
    return [];
  }
  try {
    const raw = storage.getItem(storageKey);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    const out: FjRecentSearch[] = [];
    for (const row of parsed) {
      if (!row || typeof row !== 'object') {
        continue;
      }
      const query = normalizeQuery(String((row as FjRecentSearch).query ?? ''));
      if (!query) {
        continue;
      }
      const title = (row as FjRecentSearch).title;
      const href = (row as FjRecentSearch).href;
      const at = Number((row as FjRecentSearch).at) || Date.now();
      out.push({
        query,
        title: typeof title === 'string' ? title.slice(0, 200) : undefined,
        href: typeof href === 'string' ? href.slice(0, 2048) : undefined,
        at,
      });
      if (out.length >= limit) {
        break;
      }
    }
    return out;
  } catch {
    return [];
  }
}

function writeRecentSearches(entries: readonly FjRecentSearch[], storageKey: string): void {
  const storage = safeStorage();
  if (!storage) {
    return;
  }
  try {
    storage.setItem(storageKey, JSON.stringify(entries));
  } catch {
    // Quota / private mode — ignore.
  }
}

/** Restore a prior recent-search snapshot (command-history undo). */
export function restoreRecentSearches(
  entries: readonly FjRecentSearch[],
  storageKey: string = DEFAULT_RECENT_STORAGE_KEY,
): void {
  if (!entries.length) {
    clearRecentSearches(storageKey);
    return;
  }
  writeRecentSearches(entries, storageKey);
}

/** Push a query (and optional destination) to the front of recent history. */
export function pushRecentSearch(
  entry: { query: string; title?: string; href?: string },
  options?: { readonly storageKey?: string; readonly limit?: number },
): FjRecentSearch[] {
  const storageKey = options?.storageKey ?? DEFAULT_RECENT_STORAGE_KEY;
  const limit = options?.limit ?? DEFAULT_RECENT_LIMIT;
  const query = normalizeQuery(entry.query);
  if (!query) {
    return readRecentSearches(storageKey, { limit });
  }
  const next: FjRecentSearch = {
    query,
    title: entry.title?.slice(0, 200),
    href: entry.href?.slice(0, 2048),
    at: Date.now(),
  };
  const prior = readRecentSearches(storageKey, { limit: limit * 2 }).filter((row) => {
    if (next.href && row.href) {
      return row.href !== next.href || row.query !== next.query;
    }
    return row.query !== next.query;
  });
  const merged = [next, ...prior].slice(0, limit);
  writeRecentSearches(merged, storageKey);
  return merged;
}

/** Clear all recent searches for the key. */
export function clearRecentSearches(storageKey: string = DEFAULT_RECENT_STORAGE_KEY): void {
  const storage = safeStorage();
  if (!storage) {
    return;
  }
  try {
    storage.removeItem(storageKey);
  } catch {
    // ignore
  }
}

/** Map recent rows into palette items for the empty-query state. */
export function recentSearchesAsItems(recent: readonly FjRecentSearch[]): FjSearchPaletteItem[] {
  return recent.map((row) => ({
    title: row.title || row.query,
    href: row.href || `#fj-recent:${encodeURIComponent(row.query)}`,
    snippet: row.title ? `Recent · ${row.query}` : 'Recent search',
    group: 'Recent',
    keywords: ['recent', row.query],
  }));
}
