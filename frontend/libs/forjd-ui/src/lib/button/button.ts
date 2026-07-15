import { Component, input } from '@angular/core';

/**
 * First forjd-ui primitive — keep it tiny on purpose.
 * More variants / sizes come later when we need them.
 */
@Component({
  selector: 'forjd-button',
  template: `<button [attr.type]="type()" [attr.data-variant]="variant()">
    <ng-content />
  </button>`,
  styleUrl: './button.scss',
})
export class FjButton {
  readonly variant = input<'primary' | 'ghost'>('primary');
  readonly type = input<'button' | 'submit' | 'reset'>('button');
}
