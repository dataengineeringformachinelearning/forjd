import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'forjd-empty',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'suite-empty fj-empty viking-empty' },
  template: `
    @if (title()) {
      <p class="suite-empty-title fj-empty-title viking-empty-title">{{ title() }}</p>
    }
    @if (description()) {
      <p class="suite-empty-description fj-empty-description viking-empty-description">{{ description() }}</p>
    }
    <div class="suite-empty-actions fj-empty-actions viking-empty-actions"><ng-content /></div>
  `,
})
export class FjEmpty {
  readonly title = input('Nothing here');
  readonly description = input('');
}
