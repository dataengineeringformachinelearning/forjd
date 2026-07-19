import { Component, input } from '@angular/core';

/**
 * Labeled content section — use for status blocks and landing capability cards.
 */
@Component({
  selector: 'forjd-panel',
  host: {
    role: 'region',
    '[attr.data-variant]': 'variant()',
  },
  template: `
    @if (title()) {
      <h2 class="fj-panel-title">{{ title() }}</h2>
    }
    <ng-content />
  `,
  styleUrl: './panel.scss',
})
export class FjPanel {
  readonly title = input<string>();
  readonly variant = input<'section' | 'card'>('section');
}
