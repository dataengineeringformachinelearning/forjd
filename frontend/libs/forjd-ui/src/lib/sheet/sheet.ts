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
  selector: 'forjd-sheet',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton],
  template: `
    <dialog
      #dialog
      class="suite-sheet fj-sheet"
      [attr.data-side]="side()"
      [attr.aria-label]="title() || 'Panel'"
      (close)="open.set(false)"
      (click)="onBackdrop($event)"
    >
      <header class="suite-sheet-header fj-sheet-header">
        @if (title()) {
          <h2 class="suite-sheet-title fj-sheet-title">{{ title() }}</h2>
        }
        @if (dismissible()) {
          <forjd-button variant="ghost" type="button" (click)="open.set(false)"
            >Close</forjd-button
          >
        }
      </header>
      <div class="suite-sheet-body fj-sheet-body"><ng-content /></div>
      <footer class="suite-sheet-footer fj-sheet-footer">
        <ng-content select="[sheetActions]" />
      </footer>
    </dialog>
  `,
})
export class FjSheet {
  readonly open = model(false);
  readonly title = input('');
  readonly side = input<'left' | 'right'>('right');
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
