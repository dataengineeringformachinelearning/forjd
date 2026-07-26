import { ChangeDetectionStrategy, Component, forwardRef, input, model } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

@Component({
  selector: 'forjd-switch',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => FjSwitch),
      multi: true,
    },
  ],
  template: `
    <label class="suite-switch fj-switch viking-switch">
      <input
        type="checkbox"
        role="switch"
        [checked]="checked()"
        [disabled]="disabled()"
        [attr.aria-checked]="checked()"
        (change)="onToggle($event)"
        (blur)="onTouched()"
      />
      <span
        class="suite-switch-track fj-switch-track viking-switch-track"
        aria-hidden="true"
      ></span>
      <span class="fj-switch-label">
        @if (label()) {
          {{ label() }}
        }
        <ng-content />
      </span>
    </label>
  `,
  styles: [
    `
      :host {
        display: inline-block;
      }
      .fj-switch-label:empty {
        display: none;
      }
    `,
  ],
})
export class FjSwitch implements ControlValueAccessor {
  readonly disabled = model(false);
  readonly checked = model(false);
  /** Accessible + visible name when content is not projected. */
  readonly label = input('');

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
