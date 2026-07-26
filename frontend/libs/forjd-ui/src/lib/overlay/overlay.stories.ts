import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjErrorBoundary } from '../feedback/error-boundary/error-boundary';
import { FjButton } from '../forms/button/button';
import { FjShortcutHelpService } from '../chrome/shortcuts/shortcut-help.service';
import { FjDialog } from './dialog/dialog';
import { FjSearchPalette } from './search-palette/search-palette';
import { FjSheet } from './sheet/sheet';
import { FjShortcutHelp } from './shortcut-help/shortcut-help';
import { FjToastHost, FjToastService } from './toast/toast';

@Component({
  selector: 'forjd-overlay-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjDialog, FjSheet, FjErrorBoundary],
  template: `
    <div style="display:flex;gap:var(--suite-space-2);flex-wrap:wrap">
      <forjd-button type="button" (click)="dialogOpen.set(true)">Open dialog</forjd-button>
      <forjd-button variant="secondary" type="button" (click)="sheetOpen.set(true)"
        >Open sheet</forjd-button
      >
    </div>
    <forjd-dialog [(open)]="dialogOpen" title="Confirm">
      <forjd-error-boundary>
        <p>Suite dialog chrome — identical on DEML and FORJD.</p>
      </forjd-error-boundary>
      <div dialogActions>
        <forjd-button variant="ghost" type="button" (click)="dialogOpen.set(false)"
          >Cancel</forjd-button
        >
        <forjd-button type="button" (click)="dialogOpen.set(false)">Confirm</forjd-button>
      </div>
    </forjd-dialog>
    <forjd-sheet [(open)]="sheetOpen" title="Inspector" side="right">
      <p>Sheet uses the same tokens as viking dialogs.</p>
    </forjd-sheet>
  `,
})
class OverlayDemo {
  readonly dialogOpen = signal(false);
  readonly sheetOpen = signal(false);
}

@Component({
  selector: 'forjd-toast-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjToastHost],
  template: `
    <forjd-toast-host />
    <div style="display:flex;gap:var(--suite-space-2);flex-wrap:wrap">
      <forjd-button type="button" (click)="success()">Success (low)</forjd-button>
      <forjd-button variant="secondary" type="button" (click)="info()">Info</forjd-button>
      <forjd-button variant="outline" type="button" (click)="warn()">Warning</forjd-button>
      <forjd-button variant="danger" type="button" (click)="critical()">Critical</forjd-button>
    </div>
  `,
})
class ToastDemo {
  private readonly toast = inject(FjToastService);
  success(): void {
    this.toast.success('Sealed ingest accepted', {
      description: 'Quiet confirmation — yields to higher priority.',
    });
  }
  info(): void {
    this.toast.show('Checkpoint advanced', {
      description: 'Normal priority status.',
      tone: 'info',
    });
  }
  warn(): void {
    this.toast.show('Ready probe degraded', {
      description: 'High priority — outranks quiet successes.',
      tone: 'warning',
    });
  }
  critical(): void {
    this.toast.critical('Tenant token rejected', {
      description: 'Sticky until dismissed.',
    });
  }
}

const meta: Meta = {
  title: 'Primitives/Overlay',
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj;

export const DialogAndSheet: Story = {
  render: () => ({
    template: `<forjd-overlay-demo />`,
    moduleMetadata: { imports: [OverlayDemo] },
  }),
};

export const Toast: Story = {
  render: () => ({
    template: `<forjd-toast-demo />`,
    moduleMetadata: { imports: [ToastDemo] },
  }),
};

@Component({
  selector: 'forjd-search-palette-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjSearchPalette],
  template: `
    <forjd-button type="button" (click)="open.set(true)">Open search (⌘K)</forjd-button>
    <forjd-search-palette
      [(open)]="open"
      [items]="items"
      placeholder="Search documentation, API, and product…"
    />
  `,
})
class SearchPaletteDemo {
  readonly open = signal(false);
  readonly items = [
    {
      title: 'Swagger',
      href: 'https://backend.forjd.co/docs',
      group: 'API',
      keywords: ['openapi'],
      snippet: 'Interactive OpenAPI docs',
    },
    {
      title: 'Sealed ingest',
      href: '#',
      group: 'Product',
      keywords: ['e2ee', 'ciphertext'],
      snippet: 'Ciphertext-only envelopes',
    },
  ];
}

export const SearchPalette: Story = {
  render: () => ({
    template: `<forjd-search-palette-demo />`,
    moduleMetadata: { imports: [SearchPaletteDemo] },
  }),
};

@Component({
  selector: 'forjd-shortcut-help-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjShortcutHelp],
  template: `
    <forjd-button type="button" (click)="help.show()">Open shortcuts (?)</forjd-button>
    <forjd-shortcut-help />
  `,
})
class ShortcutHelpDemo {
  readonly help = inject(FjShortcutHelpService);
}

export const ShortcutHelp: Story = {
  render: () => ({
    template: `<forjd-shortcut-help-demo />`,
    moduleMetadata: { imports: [ShortcutHelpDemo] },
  }),
};

@Component({
  selector: 'forjd-sheet-left-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjSheet],
  template: `
    <forjd-button type="button" variant="outline" (click)="open.set(true)"
      >Open left sheet</forjd-button
    >
    <forjd-sheet [(open)]="open" title="Filters" side="left">
      <p>Left-side sheet for dense filter / inspector layouts.</p>
    </forjd-sheet>
  `,
})
class SheetLeftDemo {
  readonly open = signal(false);
}

export const SheetLeft: Story = {
  name: 'Sheet / left side',
  render: () => ({
    template: `<forjd-sheet-left-demo />`,
    moduleMetadata: { imports: [SheetLeftDemo] },
  }),
};
