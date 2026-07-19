import { Component, input } from '@angular/core';

/**
 * First forjd-ui primitive — keep it tiny on purpose.
 * More variants / sizes come later when we need them.
 */
@Component({
  selector: 'forjd-button',
  template: `
    @if (href()) {
      <a
        [attr.href]="href()"
        [attr.target]="target()"
        [attr.rel]="target() === '_blank' ? 'noopener noreferrer' : null"
        [attr.data-variant]="variant()"
      >
        <ng-content />
      </a>
    } @else {
      <button [attr.type]="type()" [attr.data-variant]="variant()">
        <ng-content />
      </button>
    }
  `,
  styleUrl: './button.scss',
})
export class FjButton {
  readonly variant = input<'primary' | 'ghost'>('primary');
  readonly type = input<'button' | 'submit' | 'reset'>('button');
  /** When set, renders an anchor with the same FJORD button styles. */
  readonly href = input<string | undefined>(undefined);
  readonly target = input<'_self' | '_blank'>('_self');
}
