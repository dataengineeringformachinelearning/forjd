import { ChangeDetectionStrategy, Component, forwardRef, input, model } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

@Component({
  selector: 'forjd-checkbox',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => FjCheckbox),
      multi: true,
    },
  ],
  template: `
    <label class="suite-checkbox fj-checkbox viking-checkbox">
      <input
        type="checkbox"
        [checked]="checked()"
        [disabled]="disabled()"
        (change)="onToggle($event)"
        (blur)="onTouched()"
      />
      <span>
        <span><ng-content /></span>
        @if (description()) {
          <span class="suite-field-description viking-field-description">{{ description() }}</span>
        }
      </span>
    </label>
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class FjCheckbox implements ControlValueAccessor {
  readonly description = input('');
  readonly disabled = model(false);
  readonly checked = model(false);

  private onChange: (v: boolean) => void = () => undefined;
  protected onTouched: () => void = () => undefined;

  writeValue(v: boolean | null): void {
    this.checked.set(!!v);
  }
  registerOnChange(fn: (v: boolean) => void): void {
    this.onChange = fn;
  }
  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }
  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }
  protected onToggle(event: Event): void {
    const next = (event.target as HTMLInputElement).checked;
    this.checked.set(next);
    this.onChange(next);
  }
}
