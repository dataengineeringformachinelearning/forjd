import { isPlatformBrowser } from '@angular/common';
import { DestroyRef, Injectable, PLATFORM_ID, inject, signal } from '@angular/core';

import {
  getDefaultActivityLog,
  recordSuiteActivity,
  type SuiteActivityEntry,
} from '../../core/a11y/activity-log';
import { getDefaultDisclosureStore } from '../../core/a11y/disclosure';
import { getDefaultPreferencesStore, type SuitePreferences } from '../../core/a11y/preferences';
import {
  getDefaultShortcutRegistry,
  isEditableKeyboardTarget,
} from '../../core/a11y/keyboard-shortcuts';
import {
  applySuiteDataPack,
  downloadSuiteDataPack,
  exportSuiteDataPack,
  readSuiteDataPackFile,
} from '../../core/a11y/suite-data-pack';
import type { SuiteThemePreference } from '../../core/a11y/theme';
import { clearRecentSearches } from '../../overlay/search-palette/recent-searches';
import { FjToastService } from '../../overlay/toast/toast';
import { FjThemeService } from '../theme/theme.service';

/**
 * Suite preferences — persist + cross-tab sync; sheet open via ⌘, (ADR-0024).
 * Export / import soft chrome via suite data pack (ADR-0026).
 * Important actions → suite activity log (ADR-0027).
 */
@Injectable({ providedIn: 'root' })
export class FjPreferencesService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly destroyRef = inject(DestroyRef);
  private readonly theme = inject(FjThemeService);
  private readonly toast = inject(FjToastService, { optional: true });
  private readonly store = getDefaultPreferencesStore();
  private readonly activity = getDefaultActivityLog();

  private readonly openSignal = signal(false);
  private readonly snapshotSignal = signal<SuitePreferences>(this.store.get());
  private readonly activitySignal = signal<readonly SuiteActivityEntry[]>(this.activity.list());

  readonly open = this.openSignal.asReadonly();
  readonly snapshot = this.snapshotSignal.asReadonly();
  readonly activityEntries = this.activitySignal.asReadonly();

  constructor() {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const unbindSync = this.store.bindSync();
    const unbindActivity = this.activity.bindSync();
    const unsub = this.store.subscribe(() => {
      this.snapshotSignal.set(this.store.get());
    });
    const unsubActivity = this.activity.subscribe(() => {
      this.activitySignal.set(this.activity.list());
    });
    getDefaultShortcutRegistry().register({
      id: 'preferences',
      keys: ['Mod', ','],
      label: 'Open preferences',
      group: 'Navigation',
      description: 'Appearance and local UI preferences (ADR-0024).',
    });
    const unbindKeys = this.bindOpenShortcut();
    this.destroyRef.onDestroy(() => {
      unbindSync();
      unbindActivity();
      unsub();
      unsubActivity();
      unbindKeys();
    });
  }

  show(): void {
    this.openSignal.set(true);
  }

  hide(): void {
    this.openSignal.set(false);
  }

  setOpen(next: boolean): void {
    this.openSignal.set(next);
  }

  setTheme(preference: SuiteThemePreference): void {
    const prev = this.store.get().theme;
    this.theme.setPreference(preference);
    if (prev !== preference) {
      recordSuiteActivity({
        kind: 'preferences.theme',
        label: `Theme set to ${preference}`,
        source: 'forjd',
      });
    }
  }

  /** Collapse all advanced disclosure sections to smart defaults. */
  resetDisclosure(): void {
    getDefaultDisclosureStore().reset();
    recordSuiteActivity({
      kind: 'disclosure.reset',
      label: 'Reset advanced sections',
      source: 'forjd',
    });
  }

  clearSearchHistory(): void {
    clearRecentSearches();
    recordSuiteActivity({
      kind: 'search.clear',
      label: 'Cleared search history',
      source: 'forjd',
    });
  }

  resetAll(): void {
    this.store.reset();
    this.theme.setPreference('system', { recordHistory: false });
    getDefaultDisclosureStore().reset();
    clearRecentSearches();
    recordSuiteActivity({
      kind: 'preferences.reset',
      label: 'Reset all preferences',
      detail: 'Theme, disclosure, and search history',
      source: 'forjd',
    });
  }

  clearActivity(): void {
    this.activity.clear();
  }

  /** Download soft UI chrome as a suite data pack JSON file (ADR-0026). */
  exportDataPack(options?: { readonly includeRecentSearches?: boolean }): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const pack = exportSuiteDataPack({
      includeRecentSearches: options?.includeRecentSearches === true,
    });
    downloadSuiteDataPack(pack);
    recordSuiteActivity({
      kind: 'preferences.export',
      label: 'Exported local preferences',
      detail: options?.includeRecentSearches ? 'Included search history' : undefined,
      source: 'forjd',
    });
    this.toast?.success('Exported local preferences', {
      description: 'Soft UI chrome only — no tokens or secrets.',
    });
  }

  /** Import a suite data pack file (merge or replace). */
  async importDataPack(file: File, mode: 'merge' | 'replace' = 'merge'): Promise<boolean> {
    if (!isPlatformBrowser(this.platformId)) {
      return false;
    }
    const parsed = await readSuiteDataPackFile(file);
    if (!parsed.ok) {
      this.toast?.critical('Import failed', { description: parsed.error });
      return false;
    }
    const result = applySuiteDataPack(parsed.pack, { mode });
    if (parsed.pack.preferences) {
      this.theme.setPreference(parsed.pack.preferences.theme, {
        recordHistory: false,
      });
    }
    this.snapshotSignal.set(this.store.get());
    const label = result.applied.length ? result.applied.join(', ') : 'nothing to apply';
    recordSuiteActivity({
      kind: 'preferences.import',
      label: mode === 'replace' ? 'Replaced local data' : 'Merged local data',
      detail: label,
      source: 'forjd',
    });
    this.toast?.success(mode === 'replace' ? 'Replaced local data' : 'Merged local data', {
      description: label,
    });
    return true;
  }

  private bindOpenShortcut(): () => void {
    const doc = typeof document !== 'undefined' ? document : null;
    if (!doc) {
      return () => undefined;
    }
    const onKeydown = (event: KeyboardEvent): void => {
      if (event.defaultPrevented) {
        return;
      }
      if (!event.metaKey && !event.ctrlKey) {
        return;
      }
      if (event.key !== ',') {
        return;
      }
      if (isEditableKeyboardTarget(event.target)) {
        return;
      }
      event.preventDefault();
      this.show();
    };
    doc.addEventListener('keydown', onKeydown);
    return () => doc.removeEventListener('keydown', onKeydown);
  }
}
