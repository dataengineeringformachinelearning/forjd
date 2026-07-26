import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** One ordered step in a read-only pipeline visualization. */
export interface FjPipelineStep {
  id: string;
  title: string;
  detail?: string;
  kind?: 'process' | 'detect' | 'unknown' | string;
}

/**
 * Read-only visual sequence for sealed-stream workflow YAML steps.
 * Chrome: suite-components.css (`.suite-pipeline-flow` / triple prefixes).
 */
@Component({
  selector: 'forjd-pipeline-flow',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    role: 'list',
    class: 'suite-pipeline-flow fj-pipeline-flow viking-pipeline-flow',
    '[attr.data-orientation]': 'orientation()',
    '[attr.aria-label]': 'label()',
  },
  template: `
    @if (steps().length === 0) {
      <p class="suite-pipeline-flow__empty fj-pipeline-flow__empty" role="status">
        {{ emptyMessage() }}
      </p>
    } @else {
      @for (step of steps(); track step.id; let i = $index; let last = $last) {
        <div
          class="suite-pipeline-flow__step fj-pipeline-flow__step"
          role="listitem"
          [attr.data-kind]="step.kind || 'unknown'"
        >
          <div class="suite-pipeline-flow__rail fj-pipeline-flow__rail" aria-hidden="true">
            <span class="suite-pipeline-flow__marker fj-pipeline-flow__marker">{{ i + 1 }}</span>
            @if (!last) {
              <span class="suite-pipeline-flow__connector fj-pipeline-flow__connector"></span>
            }
          </div>
          <div class="suite-pipeline-flow__body fj-pipeline-flow__body">
            <p class="suite-pipeline-flow__title fj-pipeline-flow__title">{{ step.title }}</p>
            @if (step.detail) {
              <p class="suite-pipeline-flow__detail fj-pipeline-flow__detail">{{ step.detail }}</p>
            }
          </div>
        </div>
      }
    }
  `,
})
export class FjPipelineFlow {
  readonly steps = input<readonly FjPipelineStep[]>([]);
  readonly orientation = input<'vertical' | 'horizontal'>('horizontal');
  readonly label = input<string>('Pipeline steps');
  readonly emptyMessage = input<string>('No pipeline steps configured.');
}
