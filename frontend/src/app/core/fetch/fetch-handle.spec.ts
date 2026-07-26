import { describe, expect, it } from 'vitest';

import { createFetchHandle, fetchErrorMessage } from './fetch-handle';

describe('fetchErrorMessage', () => {
  it('prefers Error.message and string causes', () => {
    expect(fetchErrorMessage(new Error('boom'))).toBe('boom');
    expect(fetchErrorMessage('nope')).toBe('nope');
    expect(fetchErrorMessage(null, 'fallback')).toBe('fallback');
  });
});

describe('createFetchHandle', () => {
  it('runs loading → success for a throwing fetcher', async () => {
    const handle = createFetchHandle<number>();
    expect(handle.phase()).toBe('idle');

    const pending = handle.run(async () => 42);
    expect(handle.isLoading()).toBe(true);
    await expect(pending).resolves.toBe(42);

    expect(handle.isSuccess()).toBe(true);
    expect(handle.data()).toBe(42);
    expect(handle.error()).toBeNull();
  });

  it('runs loading → error when the fetcher throws', async () => {
    const handle = createFetchHandle<number>();
    await expect(
      handle.run(async () => {
        throw new Error('network down');
      }),
    ).resolves.toBeNull();

    expect(handle.isError()).toBe(true);
    expect(handle.error()).toBe('network down');
    expect(handle.data()).toBeNull();
  });

  it('settles soft domain outcomes without throwing', async () => {
    const handle = createFetchHandle<'ok', 'offline' | 'unreachable'>({
      initialPhase: 'loading',
    });
    expect(handle.isLoading()).toBe(true);

    await handle.runSettled(async () => ({ ok: false, error: 'offline' }));
    expect(handle.isError()).toBe(true);
    expect(handle.error()).toBe('offline');

    await handle.runSettled(async () => ({ ok: true, data: 'ok' }));
    expect(handle.isSuccess()).toBe(true);
    expect(handle.data()).toBe('ok');
    expect(handle.error()).toBeNull();
  });

  it('ignores stale results after abort / newer run', async () => {
    const handle = createFetchHandle<string>();
    let release!: (value: string) => void;
    const slow = new Promise<string>((resolve) => {
      release = resolve;
    });

    const first = handle.run(async () => slow);
    const second = handle.run(async () => 'fresh');
    await expect(second).resolves.toBe('fresh');
    release('stale');
    await expect(first).resolves.toBeNull();

    expect(handle.data()).toBe('fresh');
    expect(handle.isSuccess()).toBe(true);
  });

  it('fail() forces error without a round-trip', () => {
    const handle = createFetchHandle<'ok', 'offline'>();
    handle.fail('offline');
    expect(handle.isError()).toBe(true);
    expect(handle.error()).toBe('offline');
  });

  it('applySettled reconciles without a loading flash', async () => {
    const handle = createFetchHandle<'ok', 'not_ready'>({ initialPhase: 'loading' });
    handle.applySettled({ ok: true, data: 'ok' });
    expect(handle.isSuccess()).toBe(true);
    expect(handle.isLoading()).toBe(false);
    handle.applySettled({ ok: false, error: 'not_ready' });
    expect(handle.isError()).toBe(true);
    expect(handle.error()).toBe('not_ready');
  });

  it('reset() returns to idle and clears slots', async () => {
    const handle = createFetchHandle<number>();
    await handle.run(async () => 1);
    handle.reset();
    expect(handle.isIdle()).toBe(true);
    expect(handle.data()).toBeNull();
    expect(handle.error()).toBeNull();
  });

  it('abort() drops a lone in-flight run back to idle (not error)', async () => {
    const handle = createFetchHandle<number>();
    const pending = handle.run(async (signal) => {
      await new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => {
          reject(new DOMException('Aborted', 'AbortError'));
        });
      });
      return 7;
    });
    expect(handle.isLoading()).toBe(true);
    handle.abort();
    await expect(pending).resolves.toBeNull();
    expect(handle.isIdle()).toBe(true);
    expect(handle.isError()).toBe(false);
  });
});
