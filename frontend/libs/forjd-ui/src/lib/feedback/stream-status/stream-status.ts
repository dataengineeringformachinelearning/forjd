import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type FjStreamStatusPhase =
  'idle' | 'connecting' | 'updating' | 'paused' | 'delayed' | 'offline';

export type FjStreamStatusTone = 'muted' | 'accent' | 'warning' | 'danger' | 'success' | 'info';

/**
 * Calm near-real-time indicator — never claims "Live".
 * Chrome: suite-components.css (`.suite-stream-status` / triple prefixes).
 * Pulse only when ``pulse`` is true (connected + receiving ticks).
 */
@Component({
  selector: 'forjd-stream-status',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    role: 'status',
    class: 'suite-stream-status fj-stream-status viking-stream-status',
    '[attr.data-phase]': 'phase()',
    '[attr.data-tone]': 'tone()',
    '[attr.aria-label]': 'ariaLabel() || label()',
  },
  template: `
    <span
      class="suite-stream-status__dot fj-stream-status__dot badge-dot"
      [class.pulse-dot]="pulse()"
      aria-hidden="true"
    ></span>
    <span class="suite-stream-status__label fj-stream-status__label">{{ label() }}</span>
  `,
})
export class FjStreamStatus {
  readonly phase = input<FjStreamStatusPhase>('connecting');
  readonly label = input<string>('Connecting');
  readonly tone = input<FjStreamStatusTone>('muted');
  readonly pulse = input<boolean>(false);
  readonly ariaLabel = input<string>('');
}
