import { Injectable, ChangeDetectionStrategy, Component, inject } from '@angular/core';
import {
  createToastStore,
  toastPriorityFromTone,
  type ToastPriority,
} from '../../core/a11y/toast-store';

export type FjToastTone = 'info' | 'success' | 'warning' | 'danger';
export type FjToastPriority = ToastPriority;

export type FjToastAction = {
  readonly label: string;
  readonly onClick: () => void;
};

export interface FjToastMessage {
  id: number;
  title: string;
  description?: string;
  tone: FjToastTone;
  priority: FjToastPriority;
  dedupeKey?: string;
  /** Optional one-shot action (e.g. Undo) — ADR-0019. */
  action?: FjToastAction;
}

export type FjToastShowOptions = {
  description?: string;
  tone?: FjToastTone;
  /** Importance — defaults from tone (success→low, danger→critical). */
  priority?: FjToastPriority;
  durationMs?: number;
  /** Replace an in-flight toast with the same key (progress updates). */
  dedupeKey?: string;
  action?: FjToastAction;
};

@Injectable({ providedIn: 'root' })
export class FjToastService {
  private readonly store = createToastStore<FjToastMessage>({
    maxVisible: 3,
  });
  readonly messages = this.store.messages;

  show(title: string, opts?: FjToastShowOptions): number {
    const tone = opts?.tone ?? 'info';
    const priority = opts?.priority ?? toastPriorityFromTone(tone);
    return this.store.add(
      {
        id: this.store.nextId(),
        title,
        description: opts?.description,
        tone,
        priority,
        dedupeKey: opts?.dedupeKey,
        action: opts?.action,
      },
      opts?.durationMs,
    );
  }

  /** Quiet confirmation — low priority, short lived. */
  success(title: string, opts?: Omit<FjToastShowOptions, 'tone' | 'priority'>): number {
    return this.show(title, { ...opts, tone: 'success', priority: 'low' });
  }

  /** Blocking attention — sticky until dismissed unless duration set. */
  critical(title: string, opts?: Omit<FjToastShowOptions, 'tone' | 'priority'>): number {
    return this.show(title, { ...opts, tone: 'danger', priority: 'critical' });
  }

  dismiss(id: number): void {
    this.store.dismiss(id);
  }

  clear(): void {
    this.store.clear();
  }

  pause(id?: number): void {
    this.store.pause(id);
  }

  resume(id?: number): void {
    this.store.resume(id);
  }
}

/** Sonner-style host — place once near app root. Priority-ordered, hover-pauses. */
@Component({
  selector: 'forjd-toast-host',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div
      class="suite-toast-host fj-toast-host viking-toast-host"
      role="region"
      aria-label="Notifications"
      aria-live="polite"
      aria-relevant="additions text"
      aria-atomic="false"
    >
      @for (msg of messages(); track msg.id) {
        <div
          class="suite-toast fj-toast viking-toast"
          [attr.data-tone]="msg.tone"
          [attr.data-priority]="msg.priority"
          [attr.role]="msg.priority === 'critical' ? 'alert' : 'status'"
          [attr.aria-live]="msg.priority === 'critical' ? 'assertive' : 'polite'"
          (pointerenter)="toast.pause(msg.id)"
          (pointerleave)="toast.resume(msg.id)"
        >
          <div class="suite-toast-body fj-toast-body viking-toast-body">
            <p class="suite-toast-title fj-toast-title viking-toast-title">{{ msg.title }}</p>
            @if (msg.description) {
              <p class="suite-toast-description fj-toast-description viking-toast-description">
                {{ msg.description }}
              </p>
            }
          </div>
          @if (msg.action; as action) {
            <button
              type="button"
              class="suite-toast-action fj-toast-action viking-toast-action suite-btn fj-btn viking-btn"
              data-variant="ghost"
              (click)="onAction(msg.id, action)"
            >
              {{ action.label }}
            </button>
          }
          <button
            type="button"
            class="suite-btn fj-btn viking-btn"
            data-variant="ghost"
            aria-label="Dismiss notification"
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
  protected readonly messages = this.toast.messages;

  protected onAction(id: number, action: FjToastAction): void {
    action.onClick();
    this.toast.dismiss(id);
  }
}
