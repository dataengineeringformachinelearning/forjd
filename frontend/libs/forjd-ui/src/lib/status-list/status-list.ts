import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface FjStatusItem {
  name: string;
  ok: boolean;
  /** Defaults to `ok` / `down` from `ok`. */
  stateLabel?: string;
}

/**
 * Compact name + state rows for health / layer checks.
 * Chrome: suite-components.css (`.suite-status-list` / `.fj-status-list`).
 */
@Component({
  selector: 'forjd-status-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul class="suite-status-list fj-status-list viking-status-list">
      @for (item of items(); track item.name) {
        <li [attr.data-ok]="item.ok">
          <span class="suite-status-list__name fj-status-list__name viking-status-list__name">{{ item.name }}</span>
          <span class="suite-status-list__state fj-status-list__state viking-status-list__state">{{
            item.stateLabel ?? (item.ok ? 'ok' : 'down')
          }}</span>
        </li>
      }
    </ul>
  `,
})
export class FjStatusList {
  readonly items = input.required<readonly FjStatusItem[]>();
}
