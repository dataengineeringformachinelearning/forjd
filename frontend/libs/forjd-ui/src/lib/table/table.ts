import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { FjEmpty } from '../empty/empty';
import { FjSkeleton } from '../skeleton/skeleton';

export interface FjTableColumn {
  key: string;
  label: string;
}

@Component({
  selector: 'forjd-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjEmpty, FjSkeleton],
  template: `
    <div class="suite-table-wrap fj-table-wrap viking-table-wrap">
      @if (loading()) {
        <div class="suite-table-loading fj-table-loading" role="status" aria-live="polite">
          <forjd-skeleton variant="rect" height="2.5rem" />
          <forjd-skeleton variant="rect" height="2.5rem" />
          <forjd-skeleton variant="rect" height="2.5rem" />
        </div>
      } @else {
        <table class="suite-table fj-table viking-table">
          <thead>
            <tr>
              @for (col of columns(); track col.key) {
                <th scope="col">{{ col.label }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (row of rows(); track $index) {
              <tr>
                @for (col of columns(); track col.key) {
                  <td>{{ cell(row, col.key) }}</td>
                }
              </tr>
            } @empty {
              <tr>
                <td [attr.colspan]="columns().length || 1">
                  <forjd-empty [title]="emptyTitle()" [description]="emptyDescription()" />
                </td>
              </tr>
            }
          </tbody>
        </table>
      }
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
      }
      .suite-table-loading {
        display: grid;
        gap: var(--suite-space-1);
        padding: var(--suite-space-2);
      }
    `,
  ],
})
export class FjTable {
  readonly columns = input<readonly FjTableColumn[]>([]);
  readonly rows = input<readonly Record<string, unknown>[]>([]);
  readonly loading = input(false);
  readonly emptyTitle = input('No rows');
  readonly emptyDescription = input('Nothing matches this view yet.');

  protected cell(row: Record<string, unknown>, key: string): string {
    const value = row[key];
    if (value == null) return '';
    return String(value);
  }
}
