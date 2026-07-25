import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  input,
  model,
  viewChild,
} from '@angular/core';
import { FjButton } from '../button/button';

@Component({
  selector: 'forjd-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton],
  template: `
    <dialog
      #dialog
      class="suite-dialog fj-dialog viking-dialog"
      [attr.aria-label]="title() || 'Dialog'"
      (close)="open.set(false)"
      (click)="onBackdrop($event)"
    >
      <header class="suite-dialog-header fj-dialog-header viking-dialog-header">
        @if (title()) {
          <h2 class="suite-dialog-title fj-dialog-title viking-dialog-title">{{ title() }}</h2>
        }
        @if (dismissible()) {
          <forjd-button variant="ghost" type="button" (click)="open.set(false)"
            >Close</forjd-button
          >
        }
      </header>
      <div class="suite-dialog-body fj-dialog-body viking-dialog-body"><ng-content /></div>
      <footer class="suite-dialog-footer fj-dialog-footer viking-dialog-footer">
        <ng-content select="[dialogActions]" />
      </footer>
    </dialog>
  `,
})
export class FjDialog {
  readonly open = model(false);
  readonly title = input('');
  readonly dismissible = input(true);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const el = this.dialog().nativeElement;
      if (this.open()) {
        if (!el.open) el.showModal();
      } else if (el.open) {
        el.close();
      }
    });
  }

  protected onBackdrop(event: MouseEvent): void {
    if (!this.dismissible()) return;
    if (event.target === this.dialog().nativeElement) this.open.set(false);
  }
}
