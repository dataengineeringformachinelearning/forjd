import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  afterRenderEffect,
  computed,
  effect,
  input,
  model,
  output,
  signal,
  viewChild,
} from '@angular/core';

import { FjEmpty } from '../../feedback/empty/empty';
import { FjErrorState } from '../../feedback/error-state/error-state';
import { FjSkeleton } from '../../feedback/skeleton/skeleton';
import { FjBulkToolbar, type FjBulkAction } from '../bulk-toolbar/bulk-toolbar';
import { computeVirtualWindow, indicesForWindow } from '../virtual-list/virtual-window';

export type { FjBulkAction } from '../bulk-toolbar/bulk-toolbar';

export interface FjTableColumn {
  key: string;
  label: string;
}

/** Primitive cell values rendered via String(value). */
export type FjTableCellValue = string | number | boolean | bigint | null | undefined;

/** Row shape for forjd-table — stable `id` required when selectable. */
export interface FjTableRow {
  readonly id?: string | number;
  readonly [columnKey: string]: FjTableCellValue;
}

const VIRTUAL_THRESHOLD = 48;

@Component({
  selector: 'forjd-table',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjEmpty, FjErrorState, FjSkeleton, FjBulkToolbar],
  template: `
    <div class="suite-table-wrap fj-table-wrap viking-table-wrap">
      @if (selectable()) {
        <forjd-bulk-toolbar
          [count]="selectedIds().length"
          [actions]="bulkActions()"
          (actionClick)="onBulkAction($event)"
          (clear)="clearSelection()"
        />
      }
      @if (error()) {
        <forjd-error-state [title]="errorTitle()" [description]="error()" [hint]="errorHint()" />
      } @else if (loading()) {
        <div class="suite-table-loading fj-table-loading" role="status" aria-live="polite">
          <forjd-skeleton variant="rect" height="2.5rem" />
          <forjd-skeleton variant="rect" height="2.5rem" />
          <forjd-skeleton variant="rect" height="2.5rem" />
        </div>
      } @else if (useVirtual()) {
        <div
          #viewport
          class="suite-table-virtual-viewport fj-table-virtual-viewport"
          [style.max-height]="maxHeight()"
          (scroll)="onScroll()"
        >
          <table
            class="suite-table fj-table viking-table"
            [attr.data-selectable]="selectable() ? 'true' : null"
          >
            <thead>
              <tr>
                @if (selectable()) {
                  <th scope="col" class="suite-table-select fj-table-select viking-table-select">
                    <input
                      type="checkbox"
                      class="suite-checkbox fj-checkbox viking-checkbox"
                      [checked]="allSelected()"
                      [indeterminate]="someSelected()"
                      (change)="toggleAll()"
                      aria-label="Select all rows"
                    />
                  </th>
                }
                @for (col of columns(); track col.key) {
                  <th scope="col">{{ col.label }}</th>
                }
              </tr>
            </thead>
            <tbody>
              @if (padTop() > 0) {
                <tr class="suite-table-virtual-pad" aria-hidden="true">
                  <td [attr.colspan]="colSpan()" [style.height.px]="padTop()"></td>
                </tr>
              }
              @for (index of visibleIndices(); track trackIndex(index)) {
                <tr
                  [class.is-selected]="isSelectedAt(index)"
                  [attr.data-selected]="isSelectedAt(index) ? 'true' : null"
                >
                  @if (selectable()) {
                    <td class="suite-table-select fj-table-select viking-table-select">
                      <input
                        type="checkbox"
                        class="suite-checkbox fj-checkbox viking-checkbox"
                        [checked]="isSelectedAt(index)"
                        (change)="toggleRowAt(index)"
                        [attr.aria-label]="rowSelectLabel(index)"
                      />
                    </td>
                  }
                  @for (col of columns(); track col.key) {
                    <td>{{ cellAt(index, col.key) }}</td>
                  }
                </tr>
              }
              @if (padBottom() > 0) {
                <tr class="suite-table-virtual-pad" aria-hidden="true">
                  <td [attr.colspan]="colSpan()" [style.height.px]="padBottom()"></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <table
          class="suite-table fj-table viking-table"
          [attr.data-selectable]="selectable() ? 'true' : null"
        >
          <thead>
            <tr>
              @if (selectable()) {
                <th scope="col" class="suite-table-select fj-table-select viking-table-select">
                  <input
                    type="checkbox"
                    class="suite-checkbox fj-checkbox viking-checkbox"
                    [checked]="allSelected()"
                    [indeterminate]="someSelected()"
                    (change)="toggleAll()"
                    aria-label="Select all rows"
                  />
                </th>
              }
              @for (col of columns(); track col.key) {
                <th scope="col">{{ col.label }}</th>
              }
            </tr>
          </thead>
          <tbody>
            @for (row of rows(); track trackRow(row, $index); let i = $index) {
              <tr
                [class.is-selected]="isSelected(rowId(row, i))"
                [attr.data-selected]="isSelected(rowId(row, i)) ? 'true' : null"
              >
                @if (selectable()) {
                  <td class="suite-table-select fj-table-select viking-table-select">
                    <input
                      type="checkbox"
                      class="suite-checkbox fj-checkbox viking-checkbox"
                      [checked]="isSelected(rowId(row, i))"
                      (change)="toggleRow(rowId(row, i))"
                      [attr.aria-label]="selectLabel(rowId(row, i))"
                    />
                  </td>
                }
                @for (col of columns(); track col.key) {
                  <td>{{ cell(row, col.key) }}</td>
                }
              </tr>
            } @empty {
              <tr>
                <td [attr.colspan]="colSpan()">
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
      .suite-table-virtual-viewport {
        overflow: auto;
        overscroll-behavior: contain;
        width: 100%;
      }
      .suite-table-virtual-pad > td {
        padding: 0;
        border: 0;
        line-height: 0;
      }
    `,
  ],
})
export class FjTable implements OnDestroy {
  readonly columns = input<readonly FjTableColumn[]>([]);
  readonly rows = input<readonly FjTableRow[]>([]);
  /** Enable row checkboxes + bulk toolbar (ADR-0021). Rows should expose stable `id`. */
  readonly selectable = input(false);
  readonly selectedIds = model<readonly string[]>([]);
  readonly bulkActions = input<readonly FjBulkAction[]>([]);
  readonly bulkAction = output<{
    action: string;
    selectedIds: readonly string[];
  }>();
  /** Bind from `createFetchHandle.isLoading` (FORJD ADR-0011). */
  readonly loading = input(false);
  /** Bind fetch error copy when `isError`; empty = no error panel (ADR-0011). */
  readonly error = input('');
  readonly errorTitle = input('Could not load rows');
  readonly errorHint = input('');
  readonly emptyTitle = input('No rows');
  readonly emptyDescription = input('Nothing matches this view yet.');
  /** Enable windowing when row count exceeds this (default 48). */
  readonly virtualThreshold = input(VIRTUAL_THRESHOLD);
  readonly rowHeight = input(44);
  readonly maxHeight = input('28rem');
  readonly overscan = input(6);

  private readonly viewport = viewChild<ElementRef<HTMLElement>>('viewport');
  private readonly scrollTop = signal(0);
  private readonly viewportHeightPx = signal(0);
  private resizeObserver: ResizeObserver | null = null;
  private scrollRaf = 0;
  private measureRaf = 0;

  protected readonly useVirtual = computed(() => this.rows().length > this.virtualThreshold());

  protected readonly rowIds = computed(() =>
    this.rows().map((row, index) => this.rowId(row, index)),
  );

  protected readonly allSelected = computed(() => {
    const ids = this.rowIds();
    const selected = new Set(this.selectedIds());
    return ids.length > 0 && ids.every((id) => selected.has(id));
  });

  protected readonly someSelected = computed(() => {
    const ids = this.rowIds();
    const selected = new Set(this.selectedIds());
    const hits = ids.filter((id) => selected.has(id)).length;
    return hits > 0 && hits < ids.length;
  });

  protected readonly colSpan = computed(
    () => this.columns().length + (this.selectable() ? 1 : 0) || 1,
  );

  /** Private math snapshot — template binds flat indices / pads only. */
  private readonly windowMetrics = computed(() =>
    computeVirtualWindow({
      scrollTop: this.scrollTop(),
      viewportHeight: this.viewportHeightPx() || 448,
      itemCount: this.rows().length,
      itemHeight: this.rowHeight(),
      overscan: this.overscan(),
    }),
  );

  constructor() {
    afterRenderEffect(() => {
      if (this.useVirtual()) {
        this.bindViewport();
      }
    });

    // Drop selections for rows that left the dataset.
    effect(() => {
      if (!this.selectable()) {
        return;
      }
      const allow = new Set(this.rowIds());
      const next = this.selectedIds().filter((id) => allow.has(id));
      if (next.length !== this.selectedIds().length) {
        this.selectedIds.set(next);
      }
    });
  }

  protected readonly visibleIndices = computed(() => {
    const { start, end } = this.windowMetrics();
    return indicesForWindow(start, end);
  });

  protected readonly padTop = computed(() => this.windowMetrics().offsetY);
  protected readonly padBottom = computed(() => {
    const win = this.windowMetrics();
    return Math.max(0, win.totalHeight - win.offsetY - win.visibleCount * this.rowHeight());
  });

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    if (this.scrollRaf) {
      cancelAnimationFrame(this.scrollRaf);
      this.scrollRaf = 0;
    }
    if (this.measureRaf) {
      cancelAnimationFrame(this.measureRaf);
      this.measureRaf = 0;
    }
  }

  protected onScroll(): void {
    if (this.scrollRaf) {
      return;
    }
    this.scrollRaf = requestAnimationFrame(() => {
      this.scrollRaf = 0;
      const el = this.viewport()?.nativeElement;
      if (!el) {
        return;
      }
      const next = el.scrollTop;
      if (next !== this.scrollTop()) {
        this.scrollTop.set(next);
      }
    });
  }

  protected cell(row: FjTableRow, key: string): string {
    const value = row[key];
    if (value == null) return '';
    return String(value);
  }

  protected cellAt(index: number, key: string): string {
    const row = this.rows()[index];
    return row ? this.cell(row, key) : '';
  }

  protected trackIndex(index: number): string | number {
    return this.rowId(this.rows()[index] ?? {}, index);
  }

  protected trackRow(row: FjTableRow, index: number): string {
    return this.rowId(row, index);
  }

  protected rowId(row: FjTableRow, index: number): string {
    return row.id != null ? String(row.id) : `row-${index}`;
  }

  protected isSelected(id: string): boolean {
    return this.selectedIds().includes(id);
  }

  protected isSelectedAt(index: number): boolean {
    return this.isSelected(this.rowId(this.rows()[index] ?? {}, index));
  }

  protected selectLabel(id: string): string {
    return this.isSelected(id) ? `Deselect ${id}` : `Select ${id}`;
  }

  protected rowSelectLabel(index: number): string {
    return this.selectLabel(this.rowId(this.rows()[index] ?? {}, index));
  }

  protected toggleRow(id: string): void {
    const set = new Set(this.selectedIds());
    if (set.has(id)) {
      set.delete(id);
    } else {
      set.add(id);
    }
    this.selectedIds.set([...set]);
  }

  protected toggleRowAt(index: number): void {
    this.toggleRow(this.rowId(this.rows()[index] ?? {}, index));
  }

  protected toggleAll(): void {
    const ids = this.rowIds();
    if (this.allSelected()) {
      this.selectedIds.set([]);
      return;
    }
    this.selectedIds.set(ids);
  }

  protected clearSelection(): void {
    this.selectedIds.set([]);
  }

  protected onBulkAction(action: string): void {
    const selectedIds = this.selectedIds();
    if (!selectedIds.length) {
      return;
    }
    this.bulkAction.emit({ action, selectedIds });
  }

  private bindViewport(): void {
    const el = this.viewport()?.nativeElement;
    if (!el) {
      return;
    }
    this.scheduleMeasure(el);
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver?.disconnect();
      this.resizeObserver = new ResizeObserver((entries) => {
        const height = entries[0]?.contentRect.height;
        if (height != null && height !== this.viewportHeightPx()) {
          this.viewportHeightPx.set(Math.round(height));
        }
      });
      this.resizeObserver.observe(el);
    }
  }

  private scheduleMeasure(el: HTMLElement): void {
    if (this.measureRaf) {
      return;
    }
    this.measureRaf = requestAnimationFrame(() => {
      this.measureRaf = 0;
      const height = el.clientHeight;
      const top = el.scrollTop;
      if (height !== this.viewportHeightPx()) {
        this.viewportHeightPx.set(height);
      }
      if (top !== this.scrollTop()) {
        this.scrollTop.set(top);
      }
    });
  }
}
