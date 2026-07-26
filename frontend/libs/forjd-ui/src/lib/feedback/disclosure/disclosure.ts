import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';

import { getDefaultDisclosureStore, type DisclosureStore } from '../../core/a11y/disclosure';
import { createUidFactory } from '../../core/a11y/uid';

/**
 * Progressive disclosure panel — advanced content collapsed by default (ADR-0022).
 * Chrome: suite-components.css (`.suite-disclosure`) — shared focus/hover/disabled language.
 */
@Component({
  selector: 'forjd-disclosure',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- --- Disclosure surface --- -->
    <div
      class="suite-disclosure fj-disclosure viking-disclosure"
      [attr.data-open]="open() ? 'true' : 'false'"
      [attr.data-level]="level()"
    >
      <!-- --- Trigger (suite interactive contract) --- -->
      <button
        type="button"
        class="suite-disclosure-trigger fj-disclosure-trigger viking-disclosure-trigger"
        [id]="triggerId"
        [attr.aria-expanded]="open()"
        [attr.aria-controls]="panelId"
        (click)="toggle()"
      >
        <span class="suite-disclosure-copy fj-disclosure-copy viking-disclosure-copy">
          @if (badge()) {
            <span class="suite-disclosure-badge fj-disclosure-badge viking-disclosure-badge">{{
              badge()
            }}</span>
          }
          <span class="suite-disclosure-heading fj-disclosure-heading viking-disclosure-heading">{{
            heading()
          }}</span>
          @if (description()) {
            <span
              class="suite-disclosure-description fj-disclosure-description viking-disclosure-description"
              >{{ description() }}</span
            >
          }
        </span>
        <span
          class="suite-disclosure-chevron fj-disclosure-chevron viking-disclosure-chevron"
          aria-hidden="true"
        ></span>
      </button>
      @if (open()) {
        <div
          class="suite-disclosure-panel fj-disclosure-panel viking-disclosure-panel"
          [id]="panelId"
          role="region"
          [attr.aria-labelledby]="triggerId"
        >
          <ng-content />
        </div>
      }
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class FjDisclosure {
  private readonly destroyRef = inject(DestroyRef);
  private readonly nextUid = createUidFactory('fj-disclosure');
  private store: DisclosureStore = getDefaultDisclosureStore();

  /** Stable section id for persistence (e.g. `deml.settings.telemetry`). */
  readonly sectionId = input.required<string>();
  readonly heading = input.required<string>();
  readonly description = input('');
  /** Smart default when the user has never toggled this section. */
  readonly defaultOpen = input(false);
  /** Small label — default “Advanced” for progressive disclosure. */
  readonly badge = input('Advanced');
  readonly level = input<'default' | 'inset'>('default');

  protected readonly open = signal(false);
  protected readonly triggerId = this.nextUid('trigger');
  protected readonly panelId = computed(() => `${this.triggerId}-panel`);

  constructor() {
    effect(() => {
      this.open.set(this.store.isOpen(this.sectionId(), this.defaultOpen()));
    });
    const unsub = this.store.subscribe(() => {
      this.open.set(this.store.isOpen(this.sectionId(), this.defaultOpen()));
    });
    this.destroyRef.onDestroy(unsub);
  }

  protected toggle(): void {
    this.store.toggle(this.sectionId(), this.defaultOpen());
    this.open.set(this.store.isOpen(this.sectionId(), this.defaultOpen()));
  }
}
