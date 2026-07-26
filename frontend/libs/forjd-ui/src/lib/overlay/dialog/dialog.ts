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
  selector: 'forjd-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton],
  template: `
    <dialog
      #dialog
      class="suite-dialog fj-dialog viking-dialog"
      tabindex="-1"
      aria-modal="true"
      [attr.aria-labelledby]="title() ? titleId : null"
      [attr.aria-label]="title() ? null : 'Dialog'"
      (close)="onNativeClose()"
      (click)="onBackdrop($event)"
      (keydown)="onDialogKeydown($event)"
    >
      <header class="suite-dialog-header fj-dialog-header viking-dialog-header">
        @if (title()) {
          <h2 class="suite-dialog-title fj-dialog-title viking-dialog-title" [id]="titleId">
            {{ title() }}
          </h2>
        }
        @if (dismissible()) {
          <forjd-button variant="ghost" type="button" (click)="open.set(false)">Close</forjd-button>
        }
      </header>
      <div class="suite-dialog-body fj-dialog-body viking-dialog-body"><ng-content /></div>
      <footer class="suite-dialog-footer fj-dialog-footer viking-dialog-footer">
        <ng-content select="[dialogActions]" />
      </footer>
    </dialog>
  `,
})
/** Modal dialog (native `<dialog>`). See COMPONENTS.md → Overlay. */
export class FjDialog implements OnDestroy {
  /** Two-way open state (`[(open)]`). */
  readonly open = model(false);
  readonly title = input('');
  /** Escape + backdrop dismiss when true. */
  readonly dismissible = input(true);
  protected readonly titleId = forjdUid('fj-dialog-title');
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
