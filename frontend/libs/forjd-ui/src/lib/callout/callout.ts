import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import type { VikingTone } from '../badge/tones';

/** forjd-callout — suite-callout chrome; tone API matches Viking. */
@Component({
  selector: 'forjd-callout',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    role: 'note',
    class: 'suite-callout fj-callout viking-callout',
    '[attr.data-tone]': 'tone()',
  },
  template: `
    <div>
      @if (heading()) {
        <p class="suite-callout-heading fj-callout-heading viking-callout-heading">{{ heading() }}</p>
      }
      <div><ng-content /></div>
    </div>
  `,
})
export class FjCallout {
  readonly tone = input<VikingTone>('accent');
  readonly heading = input<string | undefined>(undefined);
}
