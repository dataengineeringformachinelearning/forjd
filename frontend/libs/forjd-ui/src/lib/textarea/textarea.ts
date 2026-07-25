import {
  ChangeDetectionStrategy,
  Component,
  forwardRef,
  input,
  model,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

@Component({
  selector: 'forjd-textarea',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => FjTextarea),
      multi: true,
    },
  ],
  template: `
    <textarea
      class="suite-textarea fj-textarea"
      [attr.name]="name() || null"
      [attr.placeholder]="placeholder() || null"
      [attr.rows]="rows()"
      [disabled]="disabled()"
      [value]="value()"
      (input)="onInput($event)"
      (blur)="onTouched()"
    ></textarea>
  `,
  styles: [`:host { display: block; }`],
})
export class FjTextarea implements ControlValueAccessor {
  readonly name = input('');
  readonly placeholder = input('');
  readonly rows = input(4);
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
  protected onInput(event: Event): void {
    const next = (event.target as HTMLTextAreaElement).value;
    this.value.set(next);
    this.onChange(next);
  }
}
