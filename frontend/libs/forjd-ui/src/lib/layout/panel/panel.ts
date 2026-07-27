import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * forjd-panel — section or suite-card surface.
 * Title chrome: `.suite-panel-title` in suite-components.css (Pass 7).
 */
@Component({
  selector: 'forjd-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet],
  host: {
    '[attr.role]': 'variant() === "section" && title() ? "region" : null',
    '[attr.aria-label]': 'variant() === "section" && title() ? title() : null',
    '[attr.data-variant]': 'variant()',
  },
  template: `
    <!-- --- Body projection --- -->
    <ng-template #body><ng-content /></ng-template>
    @if (variant() === 'card') {
      <!-- --- Card surface + optional title --- -->
      <div class="suite-card fj-card viking-card">
        @if (title()) {
          <h2 class="suite-panel-title fj-panel-title viking-panel-title">{{ title() }}</h2>
        }
        <ng-container [ngTemplateOutlet]="body" />
      </div>
    } @else {
      <!-- --- Section title + body --- -->
      @if (title()) {
        <h2 class="suite-panel-title fj-panel-title viking-panel-title">{{ title() }}</h2>
      }
      <ng-container [ngTemplateOutlet]="body" />
    }
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class FjPanel {
  readonly title = input<string>();
  readonly variant = input<'section' | 'card'>('section');
}
