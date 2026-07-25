import { ChangeDetectionStrategy, Component, input } from '@angular/core';

@Component({
  selector: 'forjd-separator',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-separator fj-separator',
    role: 'separator',
    '[attr.aria-orientation]': 'orientation()',
    '[attr.data-orientation]': 'orientation()',
  },
  template: ``,
})
export class FjSeparator {
  readonly orientation = input<'horizontal' | 'vertical'>('horizontal');
}
