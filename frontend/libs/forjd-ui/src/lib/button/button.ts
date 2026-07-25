import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type FjButtonVariant =
  | 'primary'
  | 'secondary'
  | 'outline'
  | 'danger'
  | 'ghost';

/** Matches viking-button variants / suite-btn chrome. */
@Component({
  selector: 'forjd-button',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet],
  template: `
    <ng-template #label><ng-content /></ng-template>
    @if (href(); as url) {
      <a
        class="suite-btn fj-btn"
        [attr.data-variant]="variant()"
        [attr.href]="disabled() ? null : url"
        [attr.target]="target()"
        [attr.rel]="target() === '_blank' ? 'noopener noreferrer' : null"
        [attr.aria-disabled]="disabled() ? 'true' : null"
        [attr.tabindex]="disabled() ? -1 : null"
      >
        <ng-container [ngTemplateOutlet]="label" />
      </a>
    } @else {
      <button
        class="suite-btn fj-btn"
        [attr.data-variant]="variant()"
        [attr.type]="type()"
        [disabled]="disabled()"
      >
        <ng-container [ngTemplateOutlet]="label" />
      </button>
    }
  `,
  styles: [
    `
      :host {
        display: inline-flex;
        max-width: 100%;
        vertical-align: middle;
      }
      :host(.fj-full) {
        display: flex;
        width: 100%;
      }
      :host(.fj-full) .suite-btn {
        width: 100%;
      }
    `,
  ],
  host: { '[class.fj-full]': 'fullWidth()' },
})
export class FjButton {
  readonly variant = input<FjButtonVariant>('primary');
  readonly type = input<'button' | 'submit' | 'reset'>('button');
  readonly href = input<string | undefined>(undefined);
  readonly target = input<'_self' | '_blank'>('_self');
  readonly disabled = input(false);
  readonly fullWidth = input(false);
}
