/**
 * Canonical client data-fetching handle — flat phase/data/error signals.
 * Presentation binds `isLoading` / `isError` / `isSuccess`; domain code owns fetchers.
 *
 * ADR: docs/adr/0011-consistent-fetch-states.md (also ADR-0010 flat state).
 */

import { computed, signal, type Signal } from '@angular/core';

/** Shared lifecycle for any client request (probe, GET, mutation read-back). */
export type FetchPhase = 'idle' | 'loading' | 'success' | 'error';

/** Soft or hard settle — prefer this over throw when the domain returns outcomes. */
export type FetchSettled<TData, TError = string> =
  { readonly ok: true; readonly data: TData } | { readonly ok: false; readonly error: TError };

export type CreateFetchHandleOptions = {
  /** Default `idle`. Use `loading` when the view probes immediately on mount. */
  readonly initialPhase?: FetchPhase;
};

export type FetchHandle<TData, TError = string> = {
  readonly phase: Signal<FetchPhase>;
  readonly data: Signal<TData | null>;
  readonly error: Signal<TError | null>;
  readonly isIdle: Signal<boolean>;
  readonly isLoading: Signal<boolean>;
  readonly isSuccess: Signal<boolean>;
  readonly isError: Signal<boolean>;
  /**
   * Run a throwing fetcher. Sets loading → success|error.
   * Superseded / aborted generations do not write success or error.
   */
  run(
    fetcher: (signal: AbortSignal) => Promise<TData>,
    mapError?: (cause: unknown) => TError,
  ): Promise<TData | null>;
  /**
   * Run a soft-settled fetcher (no throw for domain outcomes).
   * Use for `/ready`-style probes that return ok | soft-failure.
   */
  runSettled(fetcher: (signal: AbortSignal) => Promise<FetchSettled<TData, TError>>): Promise<void>;
  /** Force error without a network round-trip (e.g. offline event). */
  fail(error: TError): void;
  /**
   * Apply a settled result without entering `loading` (SWR background revalidation).
   * Does not abort an in-flight `run` / `runSettled`.
   */
  applySettled(settled: FetchSettled<TData, TError>): void;
  /** Return to idle and drop data/error (does not abort — call `abort` first if needed). */
  reset(): void;
  /**
   * Abort the in-flight request (if any).
   * If still `loading` with no successor run, returns to `idle` (DestroyRef-safe).
   */
  abort(): void;
};

// --- Error mapping ---

/** Safe string for UI error slots — never stringify tokens/ciphertext. */
export function fetchErrorMessage(cause: unknown, fallback = 'Request failed'): string {
  if (typeof cause === 'string' && cause.trim()) {
    return cause;
  }
  if (cause instanceof Error && cause.message.trim()) {
    return cause.message;
  }
  return fallback;
}

// --- Handle factory ---

/**
 * Create a local fetch handle (component- or service-owned).
 * Flat signals only — no nested `{ status, data, error }` VM object (ADR-0010).
 */
export function createFetchHandle<TData, TError = string>(
  options: CreateFetchHandleOptions = {},
): FetchHandle<TData, TError> {
  const phase = signal<FetchPhase>(options.initialPhase ?? 'idle');
  const data = signal<TData | null>(null);
  const error = signal<TError | null>(null);
  let controller: AbortController | null = null;
  let generation = 0;

  const isIdle = computed(() => phase() === 'idle');
  const isLoading = computed(() => phase() === 'loading');
  const isSuccess = computed(() => phase() === 'success');
  const isError = computed(() => phase() === 'error');

  function begin(): { signal: AbortSignal; gen: number } {
    controller?.abort();
    controller = new AbortController();
    generation += 1;
    const gen = generation;
    phase.set('loading');
    error.set(null);
    return { signal: controller.signal, gen };
  }

  function isCurrent(gen: number, signal: AbortSignal): boolean {
    return gen === generation && !signal.aborted;
  }

  async function run(
    fetcher: (signal: AbortSignal) => Promise<TData>,
    mapError: (cause: unknown) => TError = (cause) => fetchErrorMessage(cause) as TError,
  ): Promise<TData | null> {
    const { signal, gen } = begin();
    try {
      const value = await fetcher(signal);
      if (!isCurrent(gen, signal)) {
        return null;
      }
      data.set(value);
      error.set(null);
      phase.set('success');
      return value;
    } catch (cause: unknown) {
      if (!isCurrent(gen, signal)) {
        return null;
      }
      error.set(mapError(cause));
      phase.set('error');
      return null;
    }
  }

  async function runSettled(
    fetcher: (signal: AbortSignal) => Promise<FetchSettled<TData, TError>>,
  ): Promise<void> {
    const { signal, gen } = begin();
    try {
      const settled = await fetcher(signal);
      if (!isCurrent(gen, signal)) {
        return;
      }
      if (settled.ok) {
        data.set(settled.data);
        error.set(null);
        phase.set('success');
        return;
      }
      error.set(settled.error);
      phase.set('error');
    } catch (cause: unknown) {
      if (!isCurrent(gen, signal)) {
        return;
      }
      // Unexpected throw from a soft fetcher — surface as string when TError allows.
      error.set(fetchErrorMessage(cause) as TError);
      phase.set('error');
    }
  }

  function fail(next: TError): void {
    controller?.abort();
    generation += 1;
    error.set(next);
    phase.set('error');
  }

  function applySettled(settled: FetchSettled<TData, TError>): void {
    if (settled.ok) {
      data.set(settled.data);
      error.set(null);
      phase.set('success');
      return;
    }
    error.set(settled.error);
    phase.set('error');
  }

  function reset(): void {
    controller?.abort();
    generation += 1;
    phase.set('idle');
    data.set(null);
    error.set(null);
  }

  function abort(): void {
    controller?.abort();
    generation += 1;
    controller = null;
    if (phase() === 'loading') {
      phase.set('idle');
    }
  }

  return {
    phase: phase.asReadonly(),
    data: data.asReadonly(),
    error: error.asReadonly(),
    isIdle,
    isLoading,
    isSuccess,
    isError,
    run,
    runSettled,
    fail,
    applySettled,
    reset,
    abort,
  };
}
