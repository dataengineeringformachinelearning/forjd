import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'forjd-skeleton',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-skeleton fj-skeleton',
    '[attr.data-variant]': 'variant()',
    '[style.width]': 'width()',
    '[style.height]': 'height()',
    'aria-hidden': 'true',
  },
  template: ``,
})
export class FjSkeleton {
  readonly variant = input<'text' | 'rect' | 'circle'>('text');
  readonly width = input('100%');
  readonly height = input('');
}
