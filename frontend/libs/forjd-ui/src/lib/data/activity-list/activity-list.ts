import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import type { SuiteActivityEntry } from '../../core/a11y/activity-log';

/**
 * Compact activity / audit rows for soft-chrome actions (ADR-0027).
 * Chrome: suite-components.css (`.suite-activity`).
 */
@Component({
  selector: 'forjd-activity-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe],
  host: {
    class: 'suite-activity fj-activity viking-activity',
  },
  template: `
    @if (entries().length === 0) {
      <p class="suite-activity-empty fj-activity-empty viking-activity-empty">
        {{ emptyLabel() }}
      </p>
    } @else {
      <ol class="suite-activity-list fj-activity-list viking-activity-list">
        @for (entry of entries(); track entry.id) {
          <li class="suite-activity-item fj-activity-item viking-activity-item">
            <div class="suite-activity-main fj-activity-main viking-activity-main">
              <span class="suite-activity-label fj-activity-label viking-activity-label">{{
                entry.label
              }}</span>
              @if (entry.detail) {
                <span class="suite-activity-detail fj-activity-detail viking-activity-detail">{{
                  entry.detail
                }}</span>
              }
            </div>
            <time
              class="suite-activity-time fj-activity-time viking-activity-time"
              [attr.datetime]="entry.at | date: 'yyyy-MM-ddTHH:mm:ss.SSSZ'"
              >{{ entry.at | date: 'short' }}</time
            >
          </li>
        }
      </ol>
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
export class FjActivityList {
  readonly entries = input.required<readonly SuiteActivityEntry[]>();
  readonly emptyLabel = input('No recent activity yet.');
}
