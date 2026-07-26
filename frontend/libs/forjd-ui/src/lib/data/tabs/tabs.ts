import { ChangeDetectionStrategy, Component, contentChildren, input, model } from '@angular/core';
import { nextRovingIndexBothAxes } from '../../core/a11y/focus';
import { FJ_TABS, FjTabPanel } from './tab-panel';

export interface FjTabItem {
  id: string;
  label: string;
  disabled?: boolean;
}

/**
 * Tablist — suite-tab chrome shares control grid + lift/press with buttons.
 * Prefer projected `forjd-tab-panel` children (one panel per tab id).
 * Single `ng-content` fallback remains for one-panel demos only.
 */
@Component({
  selector: 'forjd-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [{ provide: FJ_TABS, useExisting: FjTabs }],
  host: { class: 'suite-tabs fj-tabs viking-tabs' },
  template: `
    <!-- --- Roving tablist --- -->
    <div
      class="suite-tabs-list fj-tabs-list viking-tabs-list"
      role="tablist"
      [attr.aria-label]="ariaLabel()"
      (keydown)="onKeydown($event)"
    >
      @for (tab of tabs(); track tab.id) {
        <button
          type="button"
          class="suite-tab fj-tab viking-tab"
          role="tab"
          [attr.id]="'tab-' + tab.id"
          [attr.aria-selected]="value() === tab.id"
          [attr.aria-controls]="'panel-' + tab.id"
          [attr.tabindex]="value() === tab.id ? 0 : -1"
          [disabled]="!!tab.disabled"
          (click)="select(tab)"
        >
          {{ tab.label }}
        </button>
      }
    </div>
    @if (panels().length > 0) {
      <!-- --- Durable per-tab panels --- -->
      <ng-content select="forjd-tab-panel" />
    } @else {
      <!-- --- Legacy single-panel slot (prefer forjd-tab-panel) --- -->
      <div
        class="suite-tab-panel fj-tab-panel viking-tab-panel"
        role="tabpanel"
        [attr.id]="'panel-' + value()"
        [attr.aria-labelledby]="'tab-' + value()"
        tabindex="0"
      >
        <ng-content />
      </div>
    }
  `,
})
export class FjTabs {
  readonly tabs = input<readonly FjTabItem[]>([]);
  readonly value = model('');
  readonly ariaLabel = input('Tabs');
  protected readonly panels = contentChildren(FjTabPanel);

  protected select(tab: FjTabItem): void {
    if (tab.disabled) return;
    this.value.set(tab.id);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const enabled = this.tabs().filter((tab) => !tab.disabled);
    if (enabled.length === 0) return;

    const currentIndex = Math.max(
      0,
      enabled.findIndex((tab) => tab.id === this.value()),
    );
    const nextIndex = nextRovingIndexBothAxes(event.key, currentIndex, enabled.length);
    if (nextIndex === null) return;

    event.preventDefault();
    const next = enabled[nextIndex];
    this.value.set(next.id);
    const root = event.currentTarget as HTMLElement | null;
    const target = root?.querySelector<HTMLElement>(`[id="tab-${next.id}"]`);
    target?.focus();
  }
}
