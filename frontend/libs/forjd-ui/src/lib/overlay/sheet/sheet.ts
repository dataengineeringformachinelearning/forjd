import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  effect,
  input,
  model,
  viewChild,
} from '@angular/core';
import { NativeDialogSession } from '../../core/a11y/dialog-session';
import { forjdUid } from '../../core/a11y/uid';
import { FjButton } from '../../forms/button/button';

@Component({
  selector: 'forjd-sheet',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton],
  template: `
    <dialog
      #dialog
      class="suite-sheet fj-sheet viking-sheet"
      tabindex="-1"
      aria-modal="true"
      [attr.data-side]="side()"
      [attr.aria-labelledby]="title() ? titleId : null"
      [attr.aria-label]="title() ? null : 'Panel'"
      (close)="onNativeClose()"
      (click)="onBackdrop($event)"
      (keydown)="onDialogKeydown($event)"
    >
      <header class="suite-sheet-header fj-sheet-header viking-sheet-header">
        @if (title()) {
          <h2 class="suite-sheet-title fj-sheet-title viking-sheet-title" [id]="titleId">
            {{ title() }}
          </h2>
        }
        @if (dismissible()) {
          <forjd-button variant="ghost" type="button" (click)="open.set(false)">Close</forjd-button>
        }
      </header>
      <div class="suite-sheet-body fj-sheet-body viking-sheet-body"><ng-content /></div>
      <footer class="suite-sheet-footer fj-sheet-footer viking-sheet-footer">
        <ng-content select="[sheetActions]" />
      </footer>
    </dialog>
  `,
})
/** Side sheet (native `<dialog>`). See COMPONENTS.md → Overlay. */
export class FjSheet implements OnDestroy {
  /** Two-way open state (`[(open)]`). */
  readonly open = model(false);
  readonly title = input('');
  /** Slide-in edge. */
  readonly side = input<'left' | 'right'>('right');
  /** Escape + backdrop dismiss when true. */
  readonly dismissible = input(true);
  protected readonly titleId = forjdUid('fj-sheet-title');
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly session = new NativeDialogSession();

  constructor() {
    effect(() => {
      this.session.syncOpen(this.dialog().nativeElement, this.open());
    });
  }

  ngOnDestroy(): void {
    this.session.destroy(this.dialog()?.nativeElement);
  }

  protected onNativeClose(): void {
    this.session.onNativeClose(() => {
      if (this.open()) this.open.set(false);
    });
  }

  protected onBackdrop(event: MouseEvent): void {
    this.session.onBackdropClick(event, this.dialog().nativeElement, this.dismissible(), () =>
      this.open.set(false),
    );
  }

  protected onDialogKeydown(event: KeyboardEvent): void {
    this.session.onKeydown(event, this.dialog().nativeElement);
  }
}
