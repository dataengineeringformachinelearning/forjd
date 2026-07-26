import {
  afterRenderEffect,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  inject,
  input,
} from '@angular/core';

import { syncFieldControlA11y } from '../../core/a11y/field-a11y';
import { forjdUid } from '../../core/a11y/uid';

/** forjd-field — label / description / error stack (Viking field anatomy). */
@Component({
  selector: 'forjd-field',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-field fj-field viking-field',
    '[class.viking-field-invalid]': '!!error()',
    '[attr.data-invalid]': 'error() ? "true" : null',
    role: 'group',
    '[attr.aria-labelledby]': 'label() ? labelId : null',
  },
  template: `
    <label class="suite-field-label-wrap viking-field-label-wrap">
      @if (label()) {
        <span
          class="suite-label fj-label suite-field-label viking-label viking-field-label"
          [id]="labelId"
        >
          {{ label() }}
          @if (required()) {
            <span aria-hidden="true">*</span>
          }
        </span>
      }
      <ng-content />
    </label>
    @if (description()) {
      <p
        class="suite-field-description fj-field-description viking-field-description"
        [id]="descriptionId"
      >
        {{ description() }}
      </p>
    }
    @if (error()) {
      <p
        class="suite-field-error fj-field-error viking-field-error"
        [id]="errorId"
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
      >
        <span class="suite-sr-only fj-sr-only viking-sr-only">Error: </span>{{ error() }}
      </p>
    }
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
/** Field stack — wrap every control; wires aria-describedby. See COMPONENTS.md. */
export class FjField {
  readonly label = input('');
  /** Helper copy under the label (not the error). */
  readonly description = input<string | undefined>(undefined);
  /** Validation message; sets aria-invalid on the projected control. */
  readonly error = input<string | undefined>(undefined);
  readonly required = input(false);

  protected readonly descriptionId = forjdUid('fj-field-description');
  protected readonly errorId = forjdUid('fj-field-error');
  protected readonly labelId = forjdUid('fj-field-label');

  private readonly host = inject(ElementRef<HTMLElement>);

  constructor() {
    afterRenderEffect(() => {
      const description = this.description();
      const error = this.error();
      syncFieldControlA11y(this.host.nativeElement, {
        descriptionId: this.descriptionId,
        errorId: this.errorId,
        hasDescription: !!description,
        hasError: !!error,
        required: this.required(),
      });
    });
  }
}
