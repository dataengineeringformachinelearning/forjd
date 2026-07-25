import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** forjd-panel — section or suite-card surface. */
@Component({
  selector: 'forjd-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet],
  host: {
    role: 'region',
    '[attr.data-variant]': 'variant()',
  },
  template: `
    <ng-template #body><ng-content /></ng-template>
    @if (variant() === 'card') {
      <div class="suite-card fj-card viking-card">
        @if (title()) {
          <h2 class="suite-panel-title fj-panel-title viking-panel-title">{{ title() }}</h2>
        }
        <ng-container [ngTemplateOutlet]="body" />
      </div>
    } @else {
      @if (title()) {
        <h2 class="suite-panel-title fj-panel-title viking-panel-title">{{ title() }}</h2>
      }
      <ng-container [ngTemplateOutlet]="body" />
    }
  `,
  styles: [`:host { display: block; }`],
})
export class FjPanel {
  readonly title = input<string>();
  readonly variant = input<'section' | 'card'>('section');
}
