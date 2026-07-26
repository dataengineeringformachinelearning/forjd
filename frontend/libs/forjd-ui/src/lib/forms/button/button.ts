import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { safeHref } from '../../core/a11y/safe-href';

export type FjButtonVariant = 'primary' | 'secondary' | 'outline' | 'danger' | 'ghost';

/**
 * Matches viking-button variants / suite-btn chrome.
 * Interaction language (hover/press/focus/disabled) lives in suite-components.css.
 */
@Component({
  selector: 'forjd-button',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet],
  template: `
    <!-- --- Suite button chrome (triple classes) --- -->
    <ng-template #label><ng-content /></ng-template>
    @if (safeUrl(); as url) {
      <a
        class="suite-btn fj-btn viking-btn"
        [attr.data-variant]="variant()"
        [attr.data-square]="square() ? 'true' : null"
        [attr.href]="disabled() ? null : url"
        [attr.target]="target()"
        [attr.rel]="target() === '_blank' ? 'noopener noreferrer' : null"
        [attr.aria-label]="ariaLabel()"
        [attr.aria-disabled]="disabled() ? 'true' : null"
        [attr.tabindex]="disabled() ? -1 : null"
      >
        <ng-container [ngTemplateOutlet]="label" />
      </a>
    } @else {
      <button
        class="suite-btn fj-btn viking-btn"
        [attr.data-variant]="variant()"
        [attr.data-square]="square() ? 'true' : null"
        [attr.type]="type()"
        [disabled]="disabled()"
        [attr.aria-label]="ariaLabel()"
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
/** Suite button — see `libs/forjd-ui/COMPONENTS.md` (Forms → forjd-button). */
export class FjButton {
  /** Visual variant (`data-variant` on `.suite-btn`). */
  readonly variant = input<FjButtonVariant>('primary');
  /** Native button type; ignored when `href` renders an anchor. */
  readonly type = input<'button' | 'submit' | 'reset'>('button');
  /** When set (and safe), renders `<a>` instead of `<button>`. */
  readonly href = input<string | undefined>(undefined);
  readonly target = input<'_self' | '_blank'>('_self');
  readonly disabled = input(false);
  /** Stretch to host width (`.fj-full`). */
  readonly fullWidth = input(false);
  /** Icon-only / square — pair with `aria-label` for voice control. */
  readonly square = input(false);
  readonly ariaLabel = input<string | null>(null, { alias: 'aria-label' });

  /** Drop javascript:/data:/protocol-relative hrefs (ADR-0013). */
  protected readonly safeUrl = computed(() => safeHref(this.href()));
}
