import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface FjTableColumn {
  key: string;
  label: string;
}

@Component({
  selector: 'forjd-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="suite-table-wrap fj-table-wrap viking-table-wrap">
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
              <td [attr.colspan]="columns().length">No rows</td>
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
  styles: [`:host { display: block; }`],
})
export class FjTable {
  readonly columns = input<readonly FjTableColumn[]>([]);
  readonly rows = input<readonly Record<string, unknown>[]>([]);

  protected cell(row: Record<string, unknown>, key: string): string {
    const value = row[key];
    if (value == null) return '';
    return String(value);
  }
}
