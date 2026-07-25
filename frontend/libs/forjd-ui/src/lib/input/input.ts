import {
  ChangeDetectionStrategy,
  Component,
  forwardRef,
  input,
  model,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

/** forjd-input — native control + suite-input chrome. */
@Component({
  selector: 'forjd-input',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => FjInput),
      multi: true,
    },
  ],
  template: `
    <input
      class="suite-input fj-input viking-input"
      [attr.type]="type()"
      [attr.name]="name() || null"
      [attr.placeholder]="placeholder() || null"
      [attr.autocomplete]="autocomplete() || null"
      [disabled]="disabled()"
      [value]="value()"
      (input)="onInput($event)"
      (blur)="onTouched()"
    />
  `,
  styles: [`:host { display: block; }`],
})
export class FjInput implements ControlValueAccessor {
  readonly type = input<'text' | 'email' | 'password' | 'url' | 'search'>('text');
  readonly name = input('');
  readonly placeholder = input('');
  readonly autocomplete = input('');
  readonly disabled = model(false);
  readonly value = model('');

  private onChange: (value: string) => void = () => undefined;
  protected onTouched: () => void = () => undefined;

  writeValue(value: string | null): void {
    this.value.set(value ?? '');
  }
  registerOnChange(fn: (value: string) => void): void {
    this.onChange = fn;
  }
  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }
  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }
  protected onInput(event: Event): void {
    const next = (event.target as HTMLInputElement).value;
    this.value.set(next);
    this.onChange(next);
  }
}
