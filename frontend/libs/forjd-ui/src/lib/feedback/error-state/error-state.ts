import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** forjd-error-state — recovery-oriented failure panel (not field errors). */
@Component({
  selector: 'forjd-error-state',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    role: 'alert',
    class: 'suite-error-state fj-error-state viking-error-state',
  },
  template: `
    <div
      class="suite-error-state-icon fj-error-state-icon viking-error-state-icon"
      aria-hidden="true"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.75"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5" />
        <path d="M12 16h.01" />
      </svg>
    </div>
    @if (title()) {
      <p class="suite-error-state-title fj-error-state-title viking-error-state-title">
        {{ title() }}
      </p>
    }
    @if (description()) {
      <p
        class="suite-error-state-description fj-error-state-description viking-error-state-description"
      >
        {{ description() }}
      </p>
    }
    @if (hint()) {
      <p class="suite-error-state-hint fj-error-state-hint viking-error-state-hint">{{ hint() }}</p>
    }
    <div class="suite-error-state-actions fj-error-state-actions viking-error-state-actions">
      <ng-content />
    </div>
  `,
})
export class FjErrorState {
  readonly title = input('Something went wrong');
  readonly description = input(
    'We could not complete that request. Try again, or contact support if it continues.',
  );
  readonly hint = input('');
}
