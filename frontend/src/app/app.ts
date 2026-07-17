import { DecimalPipe, JsonPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FjButton, FjPanel, FjStatusItem, FjStatusList } from 'forjd-ui';

import { AnomalyScoreResult, PulseApi, PulseResult, StackStatus } from './pulse-api';

@Component({
  selector: 'app-root',
  imports: [FjButton, FjPanel, FjStatusList, JsonPipe, DecimalPipe],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private readonly api = inject(PulseApi);

  protected readonly title = signal('FORJD');
  protected readonly stack = signal<StackStatus | null>(null);
  protected readonly pulse = signal<PulseResult | null>(null);
  protected readonly anomaly = signal<AnomalyScoreResult | null>(null);
  protected readonly busy = signal(false);
  protected readonly anomalyBusy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly stackChecks = computed<FjStatusItem[] | null>(() => {
    const s = this.stack();
    if (!s) return null;
    return Object.entries(s.checks).map(([name, value]) => ({
      name,
      ok: value.ok,
      stateLabel: value.ok ? 'ok' : 'down',
    }));
  });

  ngOnInit(): void {
    this.refreshStack();
  }

  protected refreshStack(): void {
    this.api.stack().subscribe({
      next: (s) => {
        this.stack.set(s);
        this.error.set(null);
      },
      error: (err: unknown) => {
        this.stack.set(null);
        this.error.set(this.errMsg(err, 'API unreachable — is the backend running?'));
      },
    });
  }

  protected runPulse(): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.pulse().subscribe({
      next: (p) => {
        this.pulse.set(p);
        this.busy.set(false);
        this.refreshStack();
      },
      error: (err: unknown) => {
        this.busy.set(false);
        this.error.set(this.errMsg(err, 'Pulse failed'));
      },
    });
  }

  protected runAnomaly(): void {
    this.anomalyBusy.set(true);
    this.error.set(null);
    this.api.fitAnomaly().subscribe({
      next: (fit) => {
        if (!fit.ok) {
          this.anomalyBusy.set(false);
          this.error.set(fit.error ?? 'Anomaly fit failed — is torch installed? (uv sync --group ml)');
          return;
        }
        this.api.scoreAnomaly().subscribe({
          next: (score) => {
            this.anomaly.set(score);
            this.anomalyBusy.set(false);
            this.refreshStack();
            if (!score.ok) {
              this.error.set(score.error ?? 'Anomaly score failed');
            }
          },
          error: (err: unknown) => {
            this.anomalyBusy.set(false);
            this.error.set(this.errMsg(err, 'Anomaly score failed'));
          },
        });
      },
      error: (err: unknown) => {
        this.anomalyBusy.set(false);
        this.error.set(this.errMsg(err, 'Anomaly fit failed'));
      },
    });
  }

  protected layerEntries(): FjStatusItem[] {
    const layers = this.pulse()?.layers;
    if (!layers) return [];
    return Object.entries(layers).map(([name, value]) => ({
      name,
      ok: Boolean(value?.ok),
      stateLabel: value?.ok ? 'ok' : 'fail',
    }));
  }

  private errMsg(err: unknown, fallback: string): string {
    if (err && typeof err === 'object' && 'message' in err) {
      return String((err as { message: unknown }).message);
    }
    return fallback;
  }
}
