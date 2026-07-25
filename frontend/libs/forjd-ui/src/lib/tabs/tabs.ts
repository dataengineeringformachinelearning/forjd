import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

export interface FjTabItem {
  id: string;
  label: string;
  disabled?: boolean;
}

@Component({
  selector: 'forjd-tabs',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'suite-tabs fj-tabs viking-tabs' },
  template: `
    <div class="suite-tabs-list fj-tabs-list viking-tabs-list" role="tablist" [attr.aria-label]="ariaLabel()">
      @for (tab of tabs(); track tab.id) {
        <button
          type="button"
          class="suite-tab fj-tab viking-tab"
          role="tab"
          [attr.id]="'tab-' + tab.id"
          [attr.aria-selected]="value() === tab.id"
          [attr.aria-controls]="'panel-' + tab.id"
          [disabled]="!!tab.disabled"
          (click)="select(tab)"
        >
          {{ tab.label }}
        </button>
      }
    </div>
    <div
      class="suite-tab-panel fj-tab-panel viking-tab-panel"
      role="tabpanel"
      [attr.id]="'panel-' + value()"
      [attr.aria-labelledby]="'tab-' + value()"
    >
      <ng-content />
    </div>
  `,
})
export class FjTabs {
  readonly tabs = input<readonly FjTabItem[]>([]);
  readonly value = model('');
  readonly ariaLabel = input('Tabs');

  protected select(tab: FjTabItem): void {
    if (tab.disabled) return;
    this.value.set(tab.id);
  }
}
