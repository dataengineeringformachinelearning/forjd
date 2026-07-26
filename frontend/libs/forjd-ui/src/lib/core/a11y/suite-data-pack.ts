/**
 * Suite data pack — export / import soft UI chrome (ADR-0026).
 * Dual-adapter: keep API aligned with viking-ui/core/suite-data-pack.
 *
 * Browser JSON only. Never secrets, tokens, auth, or ciphertext.
 * Unrelated to server `/api/v1/exports` (analytics jobs).
 */

import { getDefaultDisclosureStore } from './disclosure';
import { getDefaultOnboardingStore } from './onboarding';
import { getDefaultPreferencesStore, type SuitePreferences } from './preferences';
import { parseSuiteThemePreference, type SuiteThemePreference } from './theme';
import {
  DEFAULT_RECENT_LIMIT,
  DEFAULT_RECENT_STORAGE_KEY,
  readRecentSearches,
  restoreRecentSearches,
  type FjRecentSearch,
} from '../../overlay/search-palette/recent-searches';

export const SUITE_DATA_PACK_KIND = 'suite-data-pack' as const;
export const SUITE_DATA_PACK_VERSION = 1 as const;

const FORBIDDEN_KEY =
  /token|secret|password|fjsvc|jwt|authorization|ciphertext|apikey|api_key|bearer/i;

export type SuiteDataPackV1 = {
  readonly kind: typeof SUITE_DATA_PACK_KIND;
  readonly version: typeof SUITE_DATA_PACK_VERSION;
  readonly exportedAt: number;
  readonly preferences?: {
    readonly theme: SuiteThemePreference;
    readonly updatedAt: number;
  };
  readonly disclosure?: Readonly<Record<string, boolean>>;
  readonly onboarding?: unknown;
  readonly recentSearches?: readonly FjRecentSearch[];
};

export type ExportSuiteDataPackOptions = {
  /** Include command-palette recent queries (off by default — typed history). */
  readonly includeRecentSearches?: boolean;
  readonly recentStorageKey?: string;
};

export type ImportSuiteDataPackOptions = {
  readonly mode?: 'merge' | 'replace';
  readonly recentStorageKey?: string;
};

export type ParseSuiteDataPackResult =
  | { readonly ok: true; readonly pack: SuiteDataPackV1 }
  | { readonly ok: false; readonly error: string };

export type ApplySuiteDataPackResult = {
  readonly applied: readonly string[];
};

function assertNoForbiddenKeys(raw: Record<string, unknown>): string | null {
  for (const key of Object.keys(raw)) {
    if (FORBIDDEN_KEY.test(key)) {
      return `Refusing pack field “${key}” — secrets are not portable.`;
    }
  }
  return null;
}

function sanitizeRecent(rows: unknown): FjRecentSearch[] {
  if (!Array.isArray(rows)) {
    return [];
  }
  const out: FjRecentSearch[] = [];
  for (const row of rows) {
    if (!row || typeof row !== 'object') {
      continue;
    }
    const query = String((row as FjRecentSearch).query ?? '')
      .trim()
      .replace(/\s+/g, ' ')
      .slice(0, 120);
    if (!query) {
      continue;
    }
    const title = (row as FjRecentSearch).title;
    const href = (row as FjRecentSearch).href;
    out.push({
      query,
      title: typeof title === 'string' ? title.slice(0, 200) : undefined,
      href: typeof href === 'string' ? href.slice(0, 2048) : undefined,
      at: Number((row as FjRecentSearch).at) || Date.now(),
    });
    if (out.length >= DEFAULT_RECENT_LIMIT) {
      break;
    }
  }
  return out;
}

function sanitizeDisclosure(raw: unknown): Record<string, boolean> | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined;
  }
  const out: Record<string, boolean> = {};
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    if (!id || typeof value !== 'boolean') {
      continue;
    }
    out[String(id).slice(0, 128)] = value;
  }
  return out;
}

function sanitizePreferences(raw: unknown): SuitePreferences | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return undefined;
  }
  const row = raw as Record<string, unknown>;
  const theme =
    parseSuiteThemePreference(typeof row['theme'] === 'string' ? row['theme'] : null) ?? 'system';
  const updatedAt = Number(row['updatedAt']);
  return {
    theme,
    updatedAt: Number.isFinite(updatedAt) ? updatedAt : Date.now(),
  };
}

/** Build a portable pack from the current browser suite stores. */
export function exportSuiteDataPack(options?: ExportSuiteDataPackOptions): SuiteDataPackV1 {
  const prefs = getDefaultPreferencesStore().get();
  const pack: SuiteDataPackV1 = {
    kind: SUITE_DATA_PACK_KIND,
    version: SUITE_DATA_PACK_VERSION,
    exportedAt: Date.now(),
    preferences: { theme: prefs.theme, updatedAt: prefs.updatedAt },
    disclosure: getDefaultDisclosureStore().snapshot(),
    onboarding: getDefaultOnboardingStore().get(),
  };
  if (options?.includeRecentSearches) {
    return {
      ...pack,
      recentSearches: readRecentSearches(options.recentStorageKey ?? DEFAULT_RECENT_STORAGE_KEY),
    };
  }
  return pack;
}

/** Validate + sanitize an unknown JSON value into a pack. */
export function parseSuiteDataPack(raw: unknown): ParseSuiteDataPackResult {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ok: false, error: 'Pack must be a JSON object.' };
  }
  const row = raw as Record<string, unknown>;
  const forbidden = assertNoForbiddenKeys(row);
  if (forbidden) {
    return { ok: false, error: forbidden };
  }
  if (row['kind'] !== SUITE_DATA_PACK_KIND) {
    return { ok: false, error: 'Unrecognized pack kind.' };
  }
  if (row['version'] !== SUITE_DATA_PACK_VERSION) {
    return { ok: false, error: 'Unsupported pack version.' };
  }
  const exportedAt = Number(row['exportedAt']);
  const pack: SuiteDataPackV1 = {
    kind: SUITE_DATA_PACK_KIND,
    version: SUITE_DATA_PACK_VERSION,
    exportedAt: Number.isFinite(exportedAt) ? exportedAt : Date.now(),
    preferences: sanitizePreferences(row['preferences']),
    disclosure: sanitizeDisclosure(row['disclosure']),
    onboarding: row['onboarding'],
    recentSearches: row['recentSearches'] ? sanitizeRecent(row['recentSearches']) : undefined,
  };
  return { ok: true, pack };
}

/** Apply a parsed pack into local suite stores. */
export function applySuiteDataPack(
  pack: SuiteDataPackV1,
  options?: ImportSuiteDataPackOptions,
): ApplySuiteDataPackResult {
  const mode = options?.mode ?? 'merge';
  const applied: string[] = [];

  if (pack.preferences) {
    getDefaultPreferencesStore().patch({ theme: pack.preferences.theme });
    applied.push('preferences');
  }
  if (pack.disclosure) {
    getDefaultDisclosureStore().importMap(pack.disclosure, mode);
    applied.push('disclosure');
  }
  if (pack.onboarding != null) {
    getDefaultOnboardingStore().importState(pack.onboarding, mode);
    applied.push('onboarding');
  }
  if (pack.recentSearches) {
    const key = options?.recentStorageKey ?? DEFAULT_RECENT_STORAGE_KEY;
    if (mode === 'replace') {
      restoreRecentSearches(pack.recentSearches, key);
    } else {
      const current = readRecentSearches(key);
      const seen = new Set(current.map((r) => `${r.query}\0${r.href ?? ''}`));
      const merged = [...current];
      for (const row of pack.recentSearches) {
        const id = `${row.query}\0${row.href ?? ''}`;
        if (seen.has(id)) {
          continue;
        }
        seen.add(id);
        merged.push(row);
      }
      merged.sort((a, b) => b.at - a.at);
      restoreRecentSearches(merged.slice(0, DEFAULT_RECENT_LIMIT), key);
    }
    applied.push('recentSearches');
  }

  return { applied };
}

/** Trigger a browser download of the pack JSON. */
export function downloadSuiteDataPack(
  pack: SuiteDataPackV1,
  filename = 'suite-data-pack.json',
): void {
  if (typeof document === 'undefined') {
    return;
  }
  const blob = new Blob([JSON.stringify(pack, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

/** Read + parse a user-selected pack file. */
export async function readSuiteDataPackFile(file: File): Promise<ParseSuiteDataPackResult> {
  const text = await file.text();
  let raw: unknown;
  try {
    raw = JSON.parse(text) as unknown;
  } catch {
    return { ok: false, error: 'File is not valid JSON.' };
  }
  return parseSuiteDataPack(raw);
}
