/**
 * Priority-aware toast queue — shared shape for FjToastService / VikingToastService.
 * Non-intrusive: capped visible stack, importance ordering, dedupe, sticky critical.
 * Dual-adapter: keep API aligned with viking-ui/core/toast-store (ADR-0020).
 */

import { signal, type Signal } from '@angular/core';

export type ToastPriority = 'low' | 'normal' | 'high' | 'critical';

export type ToastStoreItem = {
  readonly id: number;
  readonly priority: ToastPriority;
  /** When set, a new toast with the same key replaces the prior one. */
  readonly dedupeKey?: string;
};

export type ToastStore<TMessage extends ToastStoreItem> = {
  readonly messages: Signal<readonly TMessage[]>;
  nextId: () => number;
  add: (message: TMessage, durationMs?: number) => number;
  dismiss: (id: number) => void;
  clear: () => void;
  /** Pause auto-dismiss (e.g. pointer hover) — non-intrusive reading time. */
  pause: (id?: number) => void;
  /** Resume auto-dismiss after pause. */
  resume: (id?: number) => void;
};

export type CreateToastStoreOptions = {
  readonly defaultDurationMs?: number;
  /** Max simultaneous toasts; lower-priority / older ones are dropped. */
  readonly maxVisible?: number;
  readonly durationByPriority?: Partial<Record<ToastPriority, number>>;
};

const PRIORITY_RANK: Record<ToastPriority, number> = {
  low: 0,
  normal: 1,
  high: 2,
  critical: 3,
};

const DEFAULT_DURATION_BY_PRIORITY: Record<ToastPriority, number> = {
  low: 2800,
  normal: 4000,
  high: 7000,
  /** Sticky until dismiss — critical must not vanish under the user. */
  critical: 0,
};

export function toastPriorityRank(priority: ToastPriority): number {
  return PRIORITY_RANK[priority] ?? 1;
}

/** Map suite tones to a default importance (callers may override). */
export function toastPriorityFromTone(tone: string | undefined | null): ToastPriority {
  switch (tone) {
    case 'danger':
      return 'critical';
    case 'warning':
      return 'high';
    case 'success':
      return 'low';
    case 'info':
    case 'accent':
    case 'muted':
    default:
      return 'normal';
  }
}

export function defaultToastDurationMs(
  priority: ToastPriority,
  overrides?: Partial<Record<ToastPriority, number>>,
): number {
  return overrides?.[priority] ?? DEFAULT_DURATION_BY_PRIORITY[priority] ?? 4000;
}

function sortByImportance<T extends ToastStoreItem>(list: readonly T[]): T[] {
  return [...list].sort((a, b) => {
    const byPriority = toastPriorityRank(b.priority) - toastPriorityRank(a.priority);
    if (byPriority !== 0) {
      return byPriority;
    }
    // Newer first within the same priority.
    return b.id - a.id;
  });
}

type TimerState = {
  remainingMs: number;
  startedAt: number;
  handle: ReturnType<typeof setTimeout> | null;
  paused: boolean;
};

export function createToastStore<TMessage extends ToastStoreItem>(options?: {
  defaultDurationMs?: number;
  maxVisible?: number;
  durationByPriority?: Partial<Record<ToastPriority, number>>;
}): ToastStore<TMessage> {
  const maxVisible = Math.max(1, options?.maxVisible ?? 3);
  const durationByPriority = {
    ...DEFAULT_DURATION_BY_PRIORITY,
    ...(options?.durationByPriority ?? {}),
  };
  const fallbackDuration = options?.defaultDurationMs ?? 4000;
  let seq = 0;
  const items = signal<TMessage[]>([]);
  const timers = new Map<number, TimerState>();

  const clearTimer = (id: number): void => {
    const state = timers.get(id);
    if (state?.handle != null) {
      clearTimeout(state.handle);
    }
    timers.delete(id);
  };

  const dismiss = (id: number): void => {
    clearTimer(id);
    items.update((list) => list.filter((m) => m.id !== id));
  };

  const schedule = (id: number, durationMs: number): void => {
    clearTimer(id);
    if (durationMs <= 0 || typeof globalThis.setTimeout !== 'function') {
      return;
    }
    const state: TimerState = {
      remainingMs: durationMs,
      startedAt: Date.now(),
      handle: null,
      paused: false,
    };
    state.handle = globalThis.setTimeout(() => dismiss(id), durationMs);
    timers.set(id, state);
  };

  return {
    messages: items.asReadonly(),
    nextId: () => ++seq,
    add: (message, durationMs) => {
      const resolvedDuration =
        durationMs ?? durationByPriority[message.priority] ?? fallbackDuration;

      items.update((list) => {
        let next = list;
        if (message.dedupeKey) {
          const prior = list.find((row) => row.dedupeKey === message.dedupeKey);
          if (prior) {
            clearTimer(prior.id);
            next = list.filter((row) => row.id !== prior.id);
          }
        }
        next = sortByImportance([...next, message]);
        while (next.length > maxVisible) {
          const evicted = next[next.length - 1]!;
          clearTimer(evicted.id);
          next = next.slice(0, -1);
        }
        return next;
      });

      schedule(message.id, resolvedDuration);
      return message.id;
    },
    dismiss,
    clear: () => {
      for (const id of timers.keys()) {
        clearTimer(id);
      }
      items.set([]);
    },
    pause: (id) => {
      const targets = id == null ? [...timers.keys()] : timers.has(id) ? [id] : [];
      for (const target of targets) {
        const state = timers.get(target);
        if (!state || state.paused || state.handle == null) {
          continue;
        }
        clearTimeout(state.handle);
        const elapsed = Date.now() - state.startedAt;
        state.remainingMs = Math.max(0, state.remainingMs - elapsed);
        state.handle = null;
        state.paused = true;
      }
    },
    resume: (id) => {
      const targets = id == null ? [...timers.keys()] : timers.has(id) ? [id] : [];
      for (const target of targets) {
        const state = timers.get(target);
        if (!state || !state.paused) {
          continue;
        }
        state.paused = false;
        if (state.remainingMs <= 0) {
          dismiss(target);
          continue;
        }
        state.startedAt = Date.now();
        state.handle = globalThis.setTimeout(() => dismiss(target), state.remainingMs);
      }
    },
  };
}
