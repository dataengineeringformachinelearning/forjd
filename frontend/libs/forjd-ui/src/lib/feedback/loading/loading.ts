import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** forjd-loading — inline loading panel with suite spinner. */
@Component({
  selector: 'forjd-loading',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    role: 'status',
    'aria-live': 'polite',
    class: 'suite-loading fj-loading viking-loading',
    '[attr.aria-label]': 'label()',
  },
  template: `
    <span class="suite-spinner fj-spinner viking-spinner" data-size="lg" aria-hidden="true"></span>
    @if (message()) {
      <p class="suite-loading-title fj-loading-title viking-loading-title">{{ message() }}</p>
    }
    @if (detail()) {
      <p class="suite-loading-text fj-loading-text viking-loading-text">{{ detail() }}</p>
    }
  `,
})
export class FjLoading {
  readonly label = input('Loading');
  readonly message = input('Working…');
  readonly detail = input('');
}

/** forjd-loading-overlay — absolute/fixed overlay with machined loading panel. */
@Component({
  selector: 'forjd-loading-overlay',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    role: 'status',
    'aria-live': 'polite',
    class: 'suite-loading-overlay fj-loading-overlay viking-loading-overlay',
    '[attr.aria-label]': 'label()',
    '[style.position]': 'full() ? "fixed" : null',
  },
  template: `
    <div class="suite-loading-backdrop" aria-hidden="true"></div>
    <div class="suite-loading-panel fj-loading-panel viking-loading-panel">
      <span
        class="suite-spinner fj-spinner viking-spinner"
        data-size="lg"
        aria-hidden="true"
      ></span>
      @if (message()) {
        <p class="suite-loading-title fj-loading-title viking-loading-title">{{ message() }}</p>
      }
      @if (detail()) {
        <p class="suite-loading-text fj-loading-text viking-loading-text">{{ detail() }}</p>
      }
    </div>
  `,
})
export class FjLoadingOverlay {
  readonly label = input('Loading');
  readonly message = input('Working…');
  readonly detail = input('');
  readonly full = input(false);
}
