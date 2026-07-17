import { Component, input } from '@angular/core';

/**
 * Labeled content section with a top rule — use for status blocks and similar.
 */
@Component({
  selector: 'forjd-panel',
  host: {
    role: 'region',
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
}
