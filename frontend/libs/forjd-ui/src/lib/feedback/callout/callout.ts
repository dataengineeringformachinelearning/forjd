import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import type { FjTone } from '../badge/tones';

/** forjd-callout — suite-callout chrome; tone API matches Viking. */
@Component({
  selector: 'forjd-callout',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '[attr.role]': 'tone() === "danger" ? "alert" : "note"',
    class: 'suite-callout fj-callout viking-callout',
    '[attr.data-tone]': 'tone()',
    '[attr.aria-live]': 'tone() === "danger" ? "assertive" : null',
  },
  template: `
    <div>
      @if (heading()) {
        <p class="suite-callout-heading fj-callout-heading viking-callout-heading">
          {{ heading() }}
        </p>
      }
      <div><ng-content /></div>
    </div>
  `,
})
export class FjCallout {
  readonly tone = input<FjTone>('accent');
  readonly heading = input<string | undefined>(undefined);
}
