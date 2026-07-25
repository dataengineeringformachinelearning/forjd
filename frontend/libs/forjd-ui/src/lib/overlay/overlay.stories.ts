import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjButton } from '../button/button';
import { FjDialog } from '../dialog/dialog';
import { FjSheet } from '../sheet/sheet';
import { FjToastHost, FjToastService } from '../toast/toast';

@Component({
  selector: 'fj-overlay-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjDialog, FjSheet],
  template: `
    <div style="display:flex;gap:var(--suite-space-2);flex-wrap:wrap">
      <forjd-button type="button" (click)="dialogOpen.set(true)">Open dialog</forjd-button>
      <forjd-button variant="secondary" type="button" (click)="sheetOpen.set(true)"
        >Open sheet</forjd-button
      >
    </div>
    <forjd-dialog [(open)]="dialogOpen" title="Confirm">
      <p>Suite dialog chrome — identical on DEML and FORJD.</p>
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
  selector: 'fj-toast-demo',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjToastHost],
  template: `
    <forjd-toast-host />
    <forjd-button type="button" (click)="ping()">Show toast</forjd-button>
  `,
})
class ToastDemo {
  private readonly toast = inject(FjToastService);
  ping(): void {
    this.toast.show('Sealed ingest accepted', {
      description: 'Projection checkpoint advanced.',
      tone: 'success',
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
    template: `<fj-overlay-demo />`,
    moduleMetadata: { imports: [OverlayDemo] },
  }),
};

export const Toast: Story = {
  render: () => ({
    template: `<fj-toast-demo />`,
    moduleMetadata: { imports: [ToastDemo] },
  }),
};
