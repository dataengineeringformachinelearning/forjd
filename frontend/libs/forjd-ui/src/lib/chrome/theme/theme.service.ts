import { isPlatformBrowser } from '@angular/common';
import { DestroyRef, Injectable, PLATFORM_ID, computed, inject, signal } from '@angular/core';
import { runOptimistic } from '../../core/a11y/optimistic';
import { getDefaultPreferencesStore } from '../../core/a11y/preferences';
import {
  type SuiteThemePreference,
  type SuiteThemeResolved,
  applySuiteTheme,
  cycleSuiteThemePreference,
  dispatchSuiteThemeChange,
  prefersDarkScheme,
  readSuiteThemePreference,
  resolveSuiteTheme,
  toggleSuiteThemePreference,
  writeSuiteThemePreference,
} from '../../core/a11y/theme';
import { FjCommandHistoryService } from '../history/command-history.service';

/** forjd ThemeService — suite light/dark/system with persistence + OS sync. */
@Injectable({ providedIn: 'root' })
export class FjThemeService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly destroyRef = inject(DestroyRef);
  private readonly history = inject(FjCommandHistoryService);
  private media: MediaQueryList | null = null;
  private readonly onMediaChange = (): void => {
    if (this.preference() !== 'system') return;
    this.applyCurrent();
  };

  private readonly preferenceSignal = signal<SuiteThemePreference>('system');
  private readonly systemDarkSignal = signal(true);

  readonly preference = this.preferenceSignal.asReadonly();
  readonly theme = computed<SuiteThemeResolved>(() =>
    resolveSuiteTheme(this.preferenceSignal(), this.systemDarkSignal()),
  );

  constructor() {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const prefs = getDefaultPreferencesStore();
    this.preferenceSignal.set(prefs.get().theme || readSuiteThemePreference());
    if (typeof window.matchMedia === 'function') {
      this.media = window.matchMedia('(prefers-color-scheme: dark)');
      this.systemDarkSignal.set(prefersDarkScheme(this.media));
      this.media.addEventListener('change', this.onMediaChange);
      this.destroyRef.onDestroy(() => {
        this.media?.removeEventListener('change', this.onMediaChange);
      });
    } else {
      this.systemDarkSignal.set(true);
    }
    // Follow preferences store (cross-tab sync owned by FjPreferencesService).
    const unsubPrefs = prefs.subscribe(() => {
      const next = prefs.get().theme;
      if (next !== this.preferenceSignal()) {
        this.preferenceSignal.set(next);
        this.applyCurrent({ preferenceChanged: true });
      }
    });
    this.destroyRef.onDestroy(unsubPrefs);
    this.applyCurrent();
  }

  /**
   * Optimistic theme change: update UI immediately, persist to storage, roll
   * back preference + DOM if storage throws (quota / private mode).
   * Successful changes join the command-history stack (⌘Z / Undo toast).
   */
  setPreference(
    preference: SuiteThemePreference,
    opts?: { readonly recordHistory?: boolean },
  ): void {
    if (preference === this.preferenceSignal()) return;
    if (!isPlatformBrowser(this.platformId)) {
      this.preferenceSignal.set(preference);
      return;
    }

    const previous = this.preferenceSignal();
    const commit = async (next: SuiteThemePreference): Promise<void> => {
      const result = await runOptimistic({
        snapshot: () => this.preferenceSignal(),
        apply: () => {
          this.preferenceSignal.set(next);
          this.applyCurrent({ preferenceChanged: true });
        },
        persist: () => {
          writeSuiteThemePreference(next);
          getDefaultPreferencesStore().patch({ theme: next }, { source: 'theme' });
        },
        rollback: (snap) => {
          this.preferenceSignal.set(snap);
          this.applyCurrent({ preferenceChanged: true });
        },
      });
      if (!result.ok) {
        throw result.error ?? new Error('Theme preference could not be saved');
      }
    };

    if (opts?.recordHistory === false) {
      void commit(preference);
      return;
    }

    void this.history.run({
      label: `Theme → ${preference}`,
      do: () => commit(preference),
      undo: () => commit(previous),
    });
  }

  toggleTheme(): void {
    this.setPreference(
      toggleSuiteThemePreference(this.preferenceSignal(), this.systemDarkSignal()),
    );
  }

  cyclePreference(): void {
    this.setPreference(cycleSuiteThemePreference(this.preferenceSignal()));
  }

  useSystemPreference(): void {
    this.setPreference('system');
  }

  private applyCurrent(opts?: { preferenceChanged?: boolean }): void {
    if (!isPlatformBrowser(this.platformId)) return;

    const systemDark = this.media ? prefersDarkScheme(this.media) : this.systemDarkSignal();
    if (systemDark !== this.systemDarkSignal()) {
      this.systemDarkSignal.set(systemDark);
    }

    const preference = this.preferenceSignal();
    const resolved = resolveSuiteTheme(preference, this.systemDarkSignal());
    const domChanged = applySuiteTheme(resolved);
    if (domChanged || opts?.preferenceChanged) {
      dispatchSuiteThemeChange({ preference, resolved });
    }
  }
}
