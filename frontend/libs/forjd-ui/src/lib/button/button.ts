import { NgTemplateOutlet } from '@angular/common';
import { Component, input } from '@angular/core';

/**
 * First forjd-ui primitive — keep it tiny on purpose.
 * More variants / sizes come later when we need them.
 *
 * Label content is captured once via ng-template: Angular will not project
 * <ng-content> from both @if / @else branches when href toggles the host.
 */
@Component({
  selector: 'forjd-button',
  imports: [NgTemplateOutlet],
  template: `
    <ng-template #label><ng-content /></ng-template>
    @if (href(); as url) {
      <a
        [attr.href]="url"
        [attr.target]="target()"
        [attr.rel]="target() === '_blank' ? 'noopener noreferrer' : null"
        [attr.data-variant]="variant()"
      >
        <ng-container [ngTemplateOutlet]="label" />
      </a>
    } @else {
      <button [attr.type]="type()" [attr.data-variant]="variant()">
        <ng-container [ngTemplateOutlet]="label" />
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
