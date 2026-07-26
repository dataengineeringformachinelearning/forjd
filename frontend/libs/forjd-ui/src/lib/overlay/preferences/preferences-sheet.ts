import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { FjPreferencesService } from '../../chrome/preferences/preferences.service';
import { FjSheet } from '../sheet/sheet';
import { FjPreferencesPanel } from './preferences-panel';

/** Preferences sheet — open via ⌘, / Ctrl+, or FjPreferencesService.show(). */
@Component({
  selector: 'forjd-preferences',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjSheet, FjPreferencesPanel],
  template: `
    <forjd-sheet
      [open]="prefs.open()"
      (openChange)="prefs.setOpen($event)"
      title="Preferences"
      side="right"
    >
      <forjd-preferences-panel />
    </forjd-sheet>
  `,
  styles: [
    `
      :host {
        display: contents;
      }
    `,
  ],
})
export class FjPreferences {
  protected readonly prefs = inject(FjPreferencesService);
}
