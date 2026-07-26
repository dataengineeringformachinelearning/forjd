import {
  ChangeDetectionStrategy,
  Component,
  InjectionToken,
  computed,
  inject,
  input,
} from '@angular/core';

/** Parent tabs contract — value() is the active tab id. */
export interface FjTabsHost {
  value(): string;
}

export const FJ_TABS = new InjectionToken<FjTabsHost>('FJ_TABS');

/**
 * Per-tab panel — only the active panel is in the a11y tree (hidden otherwise).
 * Pair with `forjd-tabs` tabs[] entries that share the same `value` id.
 */
@Component({
  selector: 'forjd-tab-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    class: 'suite-tab-panel fj-tab-panel viking-tab-panel',
    role: 'tabpanel',
    tabindex: '0',
    '[attr.id]': 'panelId()',
    '[attr.aria-labelledby]': 'tabId()',
    '[attr.hidden]': 'hidden() ? "" : null',
  },
  template: `<!-- --- Tab panel body --- --><ng-content />`,
})
export class FjTabPanel {
  private readonly tabs = inject(FJ_TABS, { optional: true });

  /** Must match a `FjTabItem.id` on the parent `forjd-tabs`. */
  readonly value = input.required<string>();

  protected readonly panelId = computed(() => `panel-${this.value()}`);
  protected readonly tabId = computed(() => `tab-${this.value()}`);
  protected readonly hidden = computed(() => (this.tabs?.value() ?? '') !== this.value());
}
