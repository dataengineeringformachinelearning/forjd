import { ChangeDetectionStrategy, Component, input, model, output } from '@angular/core';

import { runOptimistic } from '../../core/a11y/optimistic';
import { FjButton } from '../../forms/button/button';
import { FjErrorState } from '../error-state/error-state';

/**
 * forjd-error-boundary — cooperative failure isolation.
 * Flip `failed` to swap projected content for FjErrorState + Retry.
 * Optional `retryAction` runs optimistically (clear failed → action → restore on throw).
 */
@Component({
  selector: 'forjd-error-boundary',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjErrorState, FjButton],
  host: {
    class: 'suite-error-boundary fj-error-boundary',
    '[attr.data-failed]': 'failed() ? "true" : null',
  },
  template: `
    @if (failed()) {
      <forjd-error-state [title]="title()" [description]="description()" [hint]="hint()">
        <ng-content select="[errorActions]" />
        @if (showRetry()) {
          <forjd-button type="button" variant="primary" (click)="onRetry()">
            {{ retryLabel() }}
          </forjd-button>
        }
      </forjd-error-state>
    } @else {
      <ng-content />
    }
  `,
})
export class FjErrorBoundary {
  /** When true, show the recovery panel instead of projected content. */
  readonly failed = model(false);
  readonly title = input('Something went wrong');
  readonly description = input(
    'This section failed to render. Retry, or refresh the page if it continues.',
  );
  readonly hint = input('');
  readonly showRetry = input(true);
  readonly retryLabel = input('Retry');
  /**
   * Optional async/sync recovery. UI clears failure immediately; on throw the
   * failed panel is restored (optimistic retry with rollback).
   */
  readonly retryAction = input<(() => void | Promise<void>) | undefined>(undefined);
  readonly retry = output<void>();

  /** Mark this boundary failed (from async/catch or a parent). */
  markFailed(_error?: unknown): void {
    this.failed.set(true);
  }

  /** Clear failure and re-show projected content. */
  reset(): void {
    this.failed.set(false);
  }

  protected async onRetry(): Promise<void> {
    const action = this.retryAction();
    if (!action) {
      this.reset();
      this.retry.emit();
      return;
    }

    const result = await runOptimistic({
      snapshot: () => true as const,
      apply: () => this.failed.set(false),
      persist: () => action(),
      rollback: () => this.failed.set(true),
    });
    if (result.ok) {
      this.retry.emit();
    }
  }
}
