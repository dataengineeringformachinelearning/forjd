import { JsonPipe, KeyValuePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FjButton } from 'forjd-ui';

import { PulseApi, PulseResult, StackStatus } from './pulse-api';

@Component({
  selector: 'app-root',
  imports: [FjButton, JsonPipe, KeyValuePipe],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App implements OnInit {
  private readonly api = inject(PulseApi);

  protected readonly title = signal('FORJD');
  protected readonly stack = signal<StackStatus | null>(null);
  protected readonly pulse = signal<PulseResult | null>(null);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

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

  protected layerEntries(): Array<{ name: string; ok: boolean }> {
    const layers = this.pulse()?.layers;
    if (!layers) return [];
    return Object.entries(layers).map(([name, value]) => ({
      name,
      ok: Boolean(value?.ok),
    }));
  }

  private errMsg(err: unknown, fallback: string): string {
    if (err && typeof err === 'object' && 'message' in err) {
      return String((err as { message: unknown }).message);
    }
    return fallback;
  }
}
