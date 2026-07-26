import {
  ChangeDetectionStrategy,
  Component,
  input,
  model,
} from '@angular/core';

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
    <div
      class="suite-tabs-list fj-tabs-list viking-tabs-list"
      role="tablist"
      [attr.aria-label]="ariaLabel()"
      (keydown)="onKeydown($event)"
    >
      @for (tab of tabs(); track tab.id; let i = $index) {
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
    <div
      class="suite-tab-panel fj-tab-panel viking-tab-panel"
      role="tabpanel"
      [attr.id]="'panel-' + value()"
      [attr.aria-labelledby]="'tab-' + value()"
      tabindex="0"
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

  protected onKeydown(event: KeyboardEvent): void {
    const enabled = this.tabs().filter((tab) => !tab.disabled);
    if (enabled.length === 0) return;

    const currentIndex = Math.max(
      0,
      enabled.findIndex((tab) => tab.id === this.value()),
    );
    let nextIndex = currentIndex;

    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        nextIndex = (currentIndex + 1) % enabled.length;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        nextIndex = (currentIndex - 1 + enabled.length) % enabled.length;
        break;
      case 'Home':
        nextIndex = 0;
        break;
      case 'End':
        nextIndex = enabled.length - 1;
        break;
      default:
        return;
    }

    event.preventDefault();
    const next = enabled[nextIndex];
    this.value.set(next.id);
    const root = event.currentTarget as HTMLElement | null;
    const target = root?.querySelector<HTMLElement>(`[id="tab-${next.id}"]`);
    target?.focus();
  }
}
