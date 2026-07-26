import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Matches viking-card surface. Prefer forjd-card; forjd-panel remains for section+card. */
@Component({
  selector: 'forjd-card',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-card fj-card viking-card',
    '[attr.data-interactive]': 'interactive() ? "true" : null',
  },
  template: `<ng-content />`,
})
export class FjCard {
  readonly interactive = input(false);
}
