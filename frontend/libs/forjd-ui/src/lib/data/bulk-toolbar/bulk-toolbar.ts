import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';
import { FjButton } from '../../forms/button/button';

export type FjBulkAction = {
  readonly id: string;
  readonly label: string;
  /** Maps to forjd-button variant; danger actions use `danger`. */
  readonly variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  readonly disabled?: boolean;
};

/**
 * Non-modal bulk action bar — appears when list rows are selected (ADR-0021).
 * Chrome: suite-components.css (`.suite-bulk-toolbar`) — elevated surface + suite buttons.
 */
@Component({
  selector: 'forjd-bulk-toolbar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton],
  template: `
    @if (count() > 0) {
      <!-- --- Bulk selection chrome --- -->
      <div
        class="suite-bulk-toolbar fj-bulk-toolbar viking-bulk-toolbar"
        role="region"
        [attr.aria-label]="ariaLabel()"
      >
        <p class="suite-bulk-toolbar-count fj-bulk-toolbar-count viking-bulk-toolbar-count">
          {{ count() }} selected
        </p>
        <!-- --- Actions use suite-btn interaction language --- -->
        <div class="suite-bulk-toolbar-actions fj-bulk-toolbar-actions viking-bulk-toolbar-actions">
          @for (action of actions(); track action.id) {
            <forjd-button
              type="button"
              [variant]="action.variant ?? 'secondary'"
              [disabled]="action.disabled ?? false"
              (click)="actionClick.emit(action.id)"
            >
              {{ action.label }}
            </forjd-button>
          }
          <forjd-button type="button" variant="ghost" (click)="clear.emit()"> Clear </forjd-button>
        </div>
      </div>
    }
  `,
  styles: [
    `
      :host {
        display: contents;
      }
    `,
  ],
})
export class FjBulkToolbar {
  readonly count = input(0);
  readonly actions = input<readonly FjBulkAction[]>([]);
  readonly ariaLabel = input('Bulk actions');
  readonly actionClick = output<string>();
  readonly clear = output<void>();
}
