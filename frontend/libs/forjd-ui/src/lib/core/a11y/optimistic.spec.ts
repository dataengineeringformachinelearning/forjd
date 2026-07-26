import { describe, expect, it, vi } from 'vitest';

import { runOptimistic } from './optimistic';

describe('runOptimistic', () => {
  it('keeps applied state when persist succeeds', async () => {
    let value = 0;
    const result = await runOptimistic({
      snapshot: () => value,
      apply: () => {
        value = 1;
      },
      persist: () => undefined,
      rollback: (prior) => {
        value = prior;
      },
    });
    expect(result).toEqual({ ok: true });
    expect(value).toBe(1);
  });

  it('rolls back when persist throws', async () => {
    let value = 0;
    const result = await runOptimistic({
      snapshot: () => value,
      apply: () => {
        value = 1;
      },
      persist: () => {
        throw new Error('quota');
      },
      rollback: (prior) => {
        value = prior;
      },
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.error).toBeInstanceOf(Error);
    }
    expect(value).toBe(0);
  });

  it('awaits async persist before resolving ok', async () => {
    let value = 0;
    const persist = vi.fn(async () => {
      await Promise.resolve();
      value = 2;
    });
    const result = await runOptimistic({
      snapshot: () => 0,
      apply: () => {
        value = 1;
      },
      persist,
      rollback: () => {
        value = 0;
      },
    });
    expect(result).toEqual({ ok: true });
    expect(value).toBe(2);
    expect(persist).toHaveBeenCalledOnce();
  });

  it('returns persist error even if rollback throws', async () => {
    const result = await runOptimistic({
      snapshot: () => 'a',
      apply: () => undefined,
      persist: () => {
        throw new Error('persist-failed');
      },
      rollback: () => {
        throw new Error('rollback-failed');
      },
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect((result.error as Error).message).toBe('persist-failed');
    }
  });
});
