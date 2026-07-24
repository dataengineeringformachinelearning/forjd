import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface FjStatusItem {
  name: string;
  ok: boolean;
  /** Defaults to `ok` / `down` from `ok`. */
  stateLabel?: string;
}

/**
 * Compact name + state rows for health / layer checks.
 */
@Component({
  selector: 'forjd-status-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ul class="fj-status-list">
      @for (item of items(); track item.name) {
        <li [attr.data-ok]="item.ok">
          <span class="fj-status-list__name">{{ item.name }}</span>
          <span class="fj-status-list__state">{{
            item.stateLabel ?? (item.ok ? 'ok' : 'down')
          }}</span>
        </li>
      }
    </ul>
  `,
  styleUrl: './status-list.scss',
})
export class FjStatusList {
  readonly items = input.required<readonly FjStatusItem[]>();
}
