import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** forjd-field — label / description / error stack (Viking field anatomy). */
@Component({
  selector: 'forjd-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-field fj-field viking-field',
    '[class.viking-field-invalid]': '!!error()',
  },
  template: `
    <label class="suite-field-label-wrap">
      @if (label()) {
        <span class="suite-label fj-label suite-field-label">
          {{ label() }}
          @if (required()) {
            <span aria-hidden="true">*</span>
          }
        </span>
      }
      <ng-content />
    </label>
    @if (description() && !error()) {
      <p class="suite-field-description fj-field-description">{{ description() }}</p>
    }
    @if (error()) {
      <p class="suite-field-error fj-field-error" role="alert">{{ error() }}</p>
    }
  `,
  styles: [`:host { display: block; }`],
})
export class FjField {
  readonly label = input('');
  readonly description = input<string | undefined>(undefined);
  readonly error = input<string | undefined>(undefined);
  readonly required = input(false);
}
