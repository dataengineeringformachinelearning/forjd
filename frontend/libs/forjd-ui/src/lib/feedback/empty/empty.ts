import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** forjd-empty — suite empty state; helpful hierarchy + action slot. */
@Component({
  selector: 'forjd-empty',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    role: 'status',
    class: 'suite-empty fj-empty viking-empty',
    '[attr.data-density]': 'density()',
    '[attr.data-variant]': 'variant()',
  },
  template: `
    @if (showIcon()) {
      <div class="suite-empty-icon fj-empty-icon viking-empty-icon" aria-hidden="true">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.75"
          stroke-linecap="round"
          stroke-linejoin="round"
        >
          <path d="M4 7h16v12a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7z" />
          <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          <path d="M9 12h6" />
        </svg>
      </div>
    }
    @if (eyebrow()) {
      <p class="suite-empty-eyebrow fj-empty-eyebrow viking-empty-eyebrow">{{ eyebrow() }}</p>
    }
    @if (title()) {
      <p class="suite-empty-title fj-empty-title viking-empty-title">{{ title() }}</p>
    }
    @if (description()) {
      <p class="suite-empty-description fj-empty-description viking-empty-description">
        {{ description() }}
      </p>
    }
    @if (hint()) {
      <p class="suite-empty-hint fj-empty-hint viking-empty-hint">{{ hint() }}</p>
    }
    <div class="suite-empty-actions fj-empty-actions viking-empty-actions"><ng-content /></div>
  `,
})
export class FjEmpty {
  readonly title = input('No data yet');
  readonly description = input('When results arrive, they will show up here.');
  readonly hint = input('');
  readonly eyebrow = input('');
  readonly showIcon = input(true);
  readonly density = input<'default' | 'compact'>('default');
  readonly variant = input<'default' | 'inset'>('default');
}
