import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import { FjPreferencesService } from '../../chrome/preferences/preferences.service';
import type { SuiteThemePreference } from '../../core/a11y/theme';
import { FjActivityList } from '../../data/activity-list/activity-list';
import { FjButton } from '../../forms/button/button';
import { FjCallout } from '../../feedback/callout/callout';
import { FjCheckbox } from '../../forms/checkbox/checkbox';

/**
 * Preferences form body — theme, export/import, activity (ADR-0024 / 0026 / 0027).
 * Hosted in forjd-preferences sheet or any surface.
 */
@Component({
  selector: 'forjd-preferences-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjCallout, FjCheckbox, FjActivityList],
  template: `
    <div class="suite-preferences fj-preferences viking-preferences">
      <p class="suite-preferences-lede fj-preferences-lede viking-preferences-lede">
        Appearance syncs across browser tabs on this device. Nothing here is uploaded — secrets and
        API tokens stay out of preferences.
      </p>

      <section
        class="suite-preferences-section fj-preferences-section viking-preferences-section"
        aria-labelledby="fj-prefs-theme"
      >
        <h3
          id="fj-prefs-theme"
          class="suite-preferences-heading fj-preferences-heading viking-preferences-heading"
        >
          Theme
        </h3>
        <div
          class="suite-preferences-theme fj-preferences-theme viking-preferences-theme"
          role="group"
          aria-label="Theme preference"
        >
          @for (opt of themeOptions; track opt.value) {
            <forjd-button
              type="button"
              [variant]="prefs.snapshot().theme === opt.value ? 'primary' : 'outline'"
              (click)="setTheme(opt.value)"
            >
              {{ opt.label }}
            </forjd-button>
          }
        </div>
      </section>

      <section
        class="suite-preferences-section fj-preferences-section viking-preferences-section"
        aria-labelledby="fj-prefs-transfer"
      >
        <h3
          id="fj-prefs-transfer"
          class="suite-preferences-heading fj-preferences-heading viking-preferences-heading"
        >
          Export / import
        </h3>
        <p class="suite-preferences-lede fj-preferences-lede viking-preferences-lede">
          Move theme, disclosure, and onboarding progress between browsers. Soft chrome only — never
          tokens or sealed data.
        </p>
        <forjd-checkbox [checked]="includeRecent()" (checkedChange)="includeRecent.set($event)">
          Include search history
        </forjd-checkbox>
        <div class="suite-preferences-actions fj-preferences-actions viking-preferences-actions">
          <forjd-button type="button" variant="secondary" (click)="exportPack()">
            Export local data
          </forjd-button>
          <forjd-button type="button" variant="secondary" (click)="pickImport('merge')">
            Import (merge)
          </forjd-button>
          <forjd-button type="button" variant="outline" (click)="pickImport('replace')">
            Import (replace)
          </forjd-button>
        </div>
        <input
          #packFile
          type="file"
          accept="application/json,.json"
          class="suite-sr-only fj-sr-only viking-sr-only"
          (change)="onPackFile($event)"
        />
      </section>

      <section
        class="suite-preferences-section fj-preferences-section viking-preferences-section"
        aria-labelledby="fj-prefs-local"
      >
        <h3
          id="fj-prefs-local"
          class="suite-preferences-heading fj-preferences-heading viking-preferences-heading"
        >
          Local data
        </h3>
        <div class="suite-preferences-actions fj-preferences-actions viking-preferences-actions">
          <forjd-button type="button" variant="secondary" (click)="prefs.resetDisclosure()">
            Reset advanced sections
          </forjd-button>
          <forjd-button type="button" variant="secondary" (click)="prefs.clearSearchHistory()">
            Clear search history
          </forjd-button>
          <forjd-button type="button" variant="danger" (click)="prefs.resetAll()">
            Reset all preferences
          </forjd-button>
        </div>
      </section>

      <section
        class="suite-preferences-section fj-preferences-section viking-preferences-section"
        aria-labelledby="fj-prefs-activity"
      >
        <h3
          id="fj-prefs-activity"
          class="suite-preferences-heading fj-preferences-heading viking-preferences-heading"
        >
          Recent activity
        </h3>
        <p class="suite-preferences-lede fj-preferences-lede viking-preferences-lede">
          Important soft-chrome actions on this device. Metadata only — not a server audit trail.
        </p>
        <forjd-activity-list [entries]="prefs.activityEntries()" />
        @if (prefs.activityEntries().length > 0) {
          <div class="suite-preferences-actions fj-preferences-actions viking-preferences-actions">
            <forjd-button type="button" variant="ghost" (click)="prefs.clearActivity()">
              Clear activity
            </forjd-button>
          </div>
        }
      </section>

      <forjd-callout tone="info" heading="Keyboard">
        Press <span class="suite-kbd fj-kbd viking-kbd">⌘</span>/<span
          class="suite-kbd fj-kbd viking-kbd"
          >Ctrl</span
        ><span class="suite-kbd fj-kbd viking-kbd">,</span> to open preferences, or
        <span class="suite-kbd fj-kbd viking-kbd">?</span> for all shortcuts.
      </forjd-callout>
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class FjPreferencesPanel {
  protected readonly prefs = inject(FjPreferencesService);
  private readonly packFile = viewChild<ElementRef<HTMLInputElement>>('packFile');

  protected readonly includeRecent = signal(false);
  private importMode: 'merge' | 'replace' = 'merge';

  protected readonly themeOptions: {
    readonly value: SuiteThemePreference;
    readonly label: string;
  }[] = [
    { value: 'system', label: 'System' },
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
  ];

  protected setTheme(value: SuiteThemePreference): void {
    this.prefs.setTheme(value);
  }

  protected exportPack(): void {
    this.prefs.exportDataPack({
      includeRecentSearches: this.includeRecent(),
    });
  }

  protected pickImport(mode: 'merge' | 'replace'): void {
    this.importMode = mode;
    const input = this.packFile()?.nativeElement;
    if (!input) {
      return;
    }
    input.value = '';
    input.click();
  }

  protected onPackFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      return;
    }
    void this.prefs.importDataPack(file, this.importMode);
  }
}
