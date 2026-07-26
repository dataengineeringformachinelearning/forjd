/**
 * Optimistic apply → persist → rollback on failure.
 * Dual-adapter: keep API aligned with viking-ui/core/optimistic.
 */

export type OptimisticResult =
  { readonly ok: true } | { readonly ok: false; readonly error: unknown };

export type RunOptimisticOptions<TSnapshot> = {
  /** Capture prior state before apply (used only on rollback). */
  snapshot: () => TSnapshot;
  /** Immediate UI update. */
  apply: () => void;
  /** Persist / network / storage — sync or async. */
  persist: () => void | Promise<void>;
  /** Restore snapshot when persist throws. */
  rollback: (snapshot: TSnapshot) => void;
};

/**
 * Apply UI optimistically, then persist. On persist failure, rollback and
 * return `{ ok: false, error }` without rethrowing (callers may toast).
 */
export async function runOptimistic<TSnapshot>(
  options: RunOptimisticOptions<TSnapshot>,
): Promise<OptimisticResult> {
  const prior = options.snapshot();
  options.apply();
  try {
    await options.persist();
    return { ok: true };
  } catch (error: unknown) {
    try {
      options.rollback(prior);
    } catch {
      // Rollback must not mask the original persist failure.
    }
    return { ok: false, error };
  }
}
