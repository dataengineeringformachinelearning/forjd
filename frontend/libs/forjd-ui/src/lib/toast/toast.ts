import {
  Injectable,
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
} from '@angular/core';

export type FjToastTone = 'info' | 'success' | 'warning' | 'danger';

export interface FjToastMessage {
  id: number;
  title: string;
  description?: string;
  tone: FjToastTone;
}

@Injectable({ providedIn: 'root' })
export class FjToastService {
  private seq = 0;
  private readonly items = signal<FjToastMessage[]>([]);
  readonly messages = this.items.asReadonly();

  show(title: string, opts?: { description?: string; tone?: FjToastTone; durationMs?: number }): void {
    const id = ++this.seq;
    const tone = opts?.tone ?? 'info';
    this.items.update((list) => [...list, { id, title, description: opts?.description, tone }]);
    const duration = opts?.durationMs ?? 4000;
    if (duration > 0) {
      window.setTimeout(() => this.dismiss(id), duration);
    }
  }

  dismiss(id: number): void {
    this.items.update((list) => list.filter((m) => m.id !== id));
  }

  clear(): void {
    this.items.set([]);
  }
}

/** Sonner-style host — place once near app root. */
@Component({
  selector: 'forjd-toast-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="suite-toast-host fj-toast-host" aria-live="polite" aria-relevant="additions">
      @for (msg of messages(); track msg.id) {
        <div class="suite-toast fj-toast" [attr.data-tone]="msg.tone" role="status">
          <div class="suite-toast-body fj-toast-body">
            <p class="suite-toast-title fj-toast-title">{{ msg.title }}</p>
            @if (msg.description) {
              <p class="suite-toast-description fj-toast-description">{{ msg.description }}</p>
            }
          </div>
          <button
            type="button"
            class="suite-btn fj-btn"
            data-variant="ghost"
            aria-label="Dismiss"
            (click)="toast.dismiss(msg.id)"
          >
            ×
          </button>
        </div>
      }
    </div>
  `,
})
export class FjToastHost {
  protected readonly toast = inject(FjToastService);
  protected readonly messages = computed(() => this.toast.messages());
}
