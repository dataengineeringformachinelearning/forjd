import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import type { VikingTone } from './tones';

/** forjd-badge — suite-badge chrome; tone API matches viking-badge. */
@Component({
  selector: 'forjd-badge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-badge fj-badge viking-badge',
    '[attr.data-tone]': 'dataTone()',
  },
  template: `<ng-content />`,
})
export class FjBadge {
  readonly tone = input<VikingTone | 'neutral'>('neutral');

  protected readonly dataTone = computed(() => {
    const tone = this.tone();
    if (tone === 'neutral' || tone === 'muted' || tone === 'info') return null;
    if (tone === 'secondary') return 'danger';
    return tone;
  });
}
