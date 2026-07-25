import {
  ChangeDetectionStrategy,
  Component,
  forwardRef,
  input,
  model,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

export interface FjSelectOption {
  label: string;
  value: string;
  disabled?: boolean;
}

@Component({
  selector: 'forjd-select',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => FjSelect),
      multi: true,
    },
  ],
  template: `
    <select
      class="suite-select fj-select"
      [attr.name]="name() || null"
      [disabled]="disabled()"
      [value]="value()"
      (change)="onChangeEvent($event)"
      (blur)="onTouched()"
    >
      @if (placeholder()) {
        <option value="" disabled [selected]="!value()">{{ placeholder() }}</option>
      }
      @for (opt of options(); track opt.value) {
        <option [value]="opt.value" [disabled]="!!opt.disabled">{{ opt.label }}</option>
      }
    </select>
  `,
  styles: [`:host { display: block; }`],
})
export class FjSelect implements ControlValueAccessor {
  readonly name = input('');
  readonly placeholder = input('');
  readonly options = input<readonly FjSelectOption[]>([]);
  readonly disabled = model(false);
  readonly value = model('');

  private onChange: (v: string) => void = () => undefined;
  protected onTouched: () => void = () => undefined;

  writeValue(v: string | null): void {
    this.value.set(v ?? '');
  }
  registerOnChange(fn: (v: string) => void): void {
    this.onChange = fn;
  }
  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }
  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }
  protected onChangeEvent(event: Event): void {
    const next = (event.target as HTMLSelectElement).value;
    this.value.set(next);
    this.onChange(next);
  }
}
