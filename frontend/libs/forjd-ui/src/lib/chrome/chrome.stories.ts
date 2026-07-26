import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjButton } from '../forms/button/button';
import { FjPreferences } from '../overlay/preferences/preferences-sheet';
import { FjPreferencesPanel } from '../overlay/preferences/preferences-panel';
import { FjToastHost } from '../overlay/toast/toast';
import { FjPreferencesService } from './preferences/preferences.service';
import { FjThemeToggle } from './theme/theme-toggle';

@Component({
  selector: 'forjd-chrome-theme-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjThemeToggle, FjButton],
  template: `
    <div style="display:flex;align-items:center;gap:var(--suite-space-2);flex-wrap:wrap">
      <forjd-theme-toggle />
      <span style="color:var(--suite-ink-muted);font-size:var(--suite-text-sm)">
        Cycles system → light → dark (suite-preferences-v1).
      </span>
    </div>
  `,
})
class ThemeToggleDemo {}

@Component({
  selector: 'forjd-chrome-prefs-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjPreferences, FjToastHost],
  template: `
    <forjd-toast-host />
    <forjd-preferences />
    <forjd-button type="button" variant="secondary" (click)="prefs.show()">
      Open preferences
    </forjd-button>
    <p
      style="margin-top:var(--suite-space-2);color:var(--suite-ink-muted);font-size:var(--suite-text-sm)"
    >
      Sheet hosts theme, export/import, and recent activity (ADR-0024–0027). Soft chrome only.
    </p>
  `,
})
class PreferencesDemo {
  readonly prefs = inject(FjPreferencesService);
}

const meta: Meta = {
  title: 'Primitives/Chrome',
  tags: ['autodocs'],
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

export const ThemeToggle: Story = {
  render: () => ({
    template: `<forjd-chrome-theme-demo />`,
    moduleMetadata: { imports: [ThemeToggleDemo] },
  }),
};

export const PreferencesSheet: Story = {
  name: 'Preferences / sheet',
  render: () => ({
    template: `<forjd-chrome-prefs-demo />`,
    moduleMetadata: { imports: [PreferencesDemo] },
  }),
};

export const PreferencesPanel: Story = {
  name: 'Preferences / panel (embedded)',
  render: () => ({
    imports: [FjPreferencesPanel],
    template: `
      <div style="width:min(28rem,92vw);border:1px solid var(--suite-border);border-radius:var(--suite-radius-surface);padding:var(--suite-space-3)">
        <forjd-preferences-panel />
      </div>
    `,
  }),
};
