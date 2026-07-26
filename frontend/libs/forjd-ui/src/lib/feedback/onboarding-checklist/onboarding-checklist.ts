import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { recordSuiteActivity } from '../../core/a11y/activity-log';
import {
  SUITE_EMPTY_GUIDANCE_EYEBROW,
  getDefaultOnboardingStore,
  type OnboardingStore,
  type SuiteOnboardingFlow,
} from '../../core/a11y/onboarding';
import { createUidFactory } from '../../core/a11y/uid';
import { safeHref } from '../../core/a11y/safe-href';
import { FjButton } from '../../forms/button/button';

/** One checklist row for first-time guidance (ADR-0025). */
export type FjOnboardingStep = {
  readonly id: string;
  readonly title: string;
  readonly description?: string;
  readonly href?: string;
  readonly actionLabel?: string;
};

/**
 * First-time onboarding checklist — persists via createOnboardingStore (ADR-0025).
 * Chrome: suite-components.css (`.suite-onboarding`).
 * Empty surfaces should keep using forjd-empty with SUITE_EMPTY_GUIDANCE_EYEBROW.
 */
@Component({
  selector: 'forjd-onboarding-checklist',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton],
  host: {
    class: 'suite-onboarding fj-onboarding viking-onboarding',
    '[attr.data-complete]': 'allDone() ? "true" : null',
    '[hidden]': 'hidden()',
  },
  template: `
    @if (!hidden()) {
      <header class="suite-onboarding-header fj-onboarding-header viking-onboarding-header">
        <div class="suite-onboarding-copy fj-onboarding-copy viking-onboarding-copy">
          <p class="suite-onboarding-eyebrow fj-onboarding-eyebrow viking-onboarding-eyebrow">
            {{ eyebrow() }}
          </p>
          <h2
            class="suite-onboarding-title fj-onboarding-title viking-onboarding-title"
            [id]="titleId"
          >
            {{ heading() }}
          </h2>
          @if (description()) {
            <p
              class="suite-onboarding-description fj-onboarding-description viking-onboarding-description"
            >
              {{ description() }}
            </p>
          }
        </div>
        <p
          class="suite-onboarding-progress fj-onboarding-progress viking-onboarding-progress"
          aria-live="polite"
        >
          {{ completedCount() }} of {{ steps().length }} complete
        </p>
      </header>

      <ol
        class="suite-onboarding-list fj-onboarding-list viking-onboarding-list"
        [attr.aria-labelledby]="titleId"
      >
        @for (step of steps(); track step.id) {
          <li
            class="suite-onboarding-item fj-onboarding-item viking-onboarding-item"
            [attr.data-done]="isDone(step.id) ? 'true' : null"
          >
            <label class="suite-onboarding-row fj-onboarding-row viking-onboarding-row">
              <input
                type="checkbox"
                class="suite-onboarding-check fj-onboarding-check viking-onboarding-check"
                [checked]="isDone(step.id)"
                (change)="toggleStep(step.id, $event)"
              />
              <span class="suite-onboarding-body fj-onboarding-body viking-onboarding-body">
                <span
                  class="suite-onboarding-step-title fj-onboarding-step-title viking-onboarding-step-title"
                  >{{ step.title }}</span
                >
                @if (step.description) {
                  <span
                    class="suite-onboarding-step-detail fj-onboarding-step-detail viking-onboarding-step-detail"
                    >{{ step.description }}</span
                  >
                }
              </span>
            </label>
            @if (stepHref(step); as href) {
              <a
                class="suite-onboarding-action fj-onboarding-action viking-onboarding-action"
                [href]="href"
                (click)="onAction(step.id)"
              >
                {{ step.actionLabel || 'Open' }}
              </a>
            }
          </li>
        }
      </ol>

      <footer class="suite-onboarding-footer fj-onboarding-footer viking-onboarding-footer">
        @if (allDone()) {
          <forjd-button type="button" variant="primary" (click)="finish()">
            {{ finishLabel() }}
          </forjd-button>
        }
        @if (dismissible()) {
          <forjd-button type="button" variant="ghost" (click)="dismiss()">
            {{ dismissLabel() }}
          </forjd-button>
        }
      </footer>
    }
  `,
  styles: [
    `
      :host {
        display: block;
      }
      :host[hidden] {
        display: none;
      }
    `,
  ],
})
/**
 * First-time / deploy checklist (ADR-0025). Persist via `suite-onboarding-v1`.
 * See COMPONENTS.md → Feedback → forjd-onboarding-checklist.
 */
export class FjOnboardingChecklist {
  private readonly destroyRef = inject(DestroyRef);
  private readonly nextUid = createUidFactory('fj-onboarding');
  private store: OnboardingStore = getDefaultOnboardingStore();

  /** Optional flow key for multi-guide stores. */
  readonly flowId = input<SuiteOnboardingFlow>(null);
  readonly heading = input('Getting started');
  readonly description = input('');
  readonly eyebrow = input(SUITE_EMPTY_GUIDANCE_EYEBROW);
  readonly steps = input.required<readonly FjOnboardingStep[]>();
  readonly dismissible = input(true);
  readonly dismissLabel = input('Dismiss');
  readonly finishLabel = input("I'm done");
  /** Hide when the store says the guide should not show (completed / dismissed). */
  readonly autoHide = input(true);

  readonly stepChange = output<{ readonly id: string; readonly complete: boolean }>();
  readonly dismissed = output<void>();
  readonly completed = output<void>();

  protected readonly titleId = this.nextUid('title');
  protected readonly tick = signal(0);

  protected readonly completedCount = computed(() => {
    this.tick();
    return this.steps().filter((s) => this.store.isStepComplete(s.id)).length;
  });

  protected readonly allDone = computed(() => {
    this.tick();
    const list = this.steps();
    return list.length > 0 && list.every((s) => this.store.isStepComplete(s.id));
  });

  protected readonly hidden = computed(() => {
    this.tick();
    if (!this.autoHide()) {
      return false;
    }
    return !this.store.shouldShowGuide();
  });

  constructor() {
    effect(() => {
      const flow = this.flowId();
      if (flow) {
        this.store.setActiveFlow(flow);
      }
    });
    const unsub = this.store.subscribe(() => {
      this.tick.update((n) => n + 1);
    });
    this.destroyRef.onDestroy(unsub);
  }

  protected isDone(id: string): boolean {
    this.tick();
    return this.store.isStepComplete(id);
  }

  protected stepHref(step: FjOnboardingStep): string | null {
    if (!step.href) {
      return null;
    }
    return safeHref(step.href);
  }

  protected toggleStep(id: string, event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    if (checked) {
      this.store.completeStep(id);
    } else {
      this.store.incompleteStep(id);
    }
    this.stepChange.emit({ id, complete: checked });
    this.tick.update((n) => n + 1);
  }

  protected onAction(id: string): void {
    this.store.completeStep(id);
    this.stepChange.emit({ id, complete: true });
    this.tick.update((n) => n + 1);
  }

  protected finish(): void {
    this.store.markComplete();
    recordSuiteActivity({
      kind: 'onboarding.complete',
      label: 'Completed onboarding checklist',
      detail: this.flowId() ?? undefined,
      source: 'forjd',
    });
    this.completed.emit();
    this.tick.update((n) => n + 1);
  }

  protected dismiss(): void {
    this.store.markDismissed();
    recordSuiteActivity({
      kind: 'onboarding.dismiss',
      label: 'Dismissed onboarding checklist',
      detail: this.flowId() ?? undefined,
      source: 'forjd',
    });
    this.dismissed.emit();
    this.tick.update((n) => n + 1);
  }
}
