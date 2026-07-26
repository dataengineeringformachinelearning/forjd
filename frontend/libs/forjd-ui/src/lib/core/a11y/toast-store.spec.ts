import { describe, expect, it, vi } from 'vitest';
import { createToastStore, toastPriorityFromTone, type ToastPriority } from './toast-store';

type Msg = {
  id: number;
  title: string;
  priority: ToastPriority;
  dedupeKey?: string;
};

describe('createToastStore', () => {
  it('queues, dismisses, and clears messages', () => {
    vi.useFakeTimers();
    const store = createToastStore<Msg>({ defaultDurationMs: 1000 });

    const id = store.add({
      id: store.nextId(),
      title: 'hello',
      priority: 'normal',
    });
    expect(store.messages()).toHaveLength(1);
    expect(id).toBe(1);

    store.dismiss(id);
    expect(store.messages()).toHaveLength(0);

    store.add({ id: store.nextId(), title: 'auto', priority: 'normal' }, 500);
    expect(store.messages()).toHaveLength(1);
    vi.advanceTimersByTime(500);
    expect(store.messages()).toHaveLength(0);

    store.add({ id: store.nextId(), title: 'keep', priority: 'critical' }, 0);
    store.clear();
    expect(store.messages()).toHaveLength(0);
    vi.useRealTimers();
  });

  it('orders by priority and caps visible stack', () => {
    const store = createToastStore<Msg>({ maxVisible: 2 });
    store.add({ id: store.nextId(), title: 'low', priority: 'low' }, 0);
    store.add({ id: store.nextId(), title: 'normal', priority: 'normal' }, 0);
    store.add({ id: store.nextId(), title: 'critical', priority: 'critical' }, 0);

    const titles = store.messages().map((m) => m.title);
    expect(titles).toEqual(['critical', 'normal']);
  });

  it('dedupes by key and pauses auto-dismiss on hover', () => {
    vi.useFakeTimers();
    const store = createToastStore<Msg>();
    store.add(
      {
        id: store.nextId(),
        title: 'saving',
        priority: 'normal',
        dedupeKey: 'save',
      },
      1000,
    );
    store.add(
      {
        id: store.nextId(),
        title: 'saved',
        priority: 'low',
        dedupeKey: 'save',
      },
      1000,
    );
    expect(store.messages()).toHaveLength(1);
    expect(store.messages()[0]?.title).toBe('saved');

    const id = store.messages()[0]!.id;
    store.pause(id);
    vi.advanceTimersByTime(2000);
    expect(store.messages()).toHaveLength(1);
    store.resume(id);
    vi.advanceTimersByTime(1000);
    expect(store.messages()).toHaveLength(0);
    vi.useRealTimers();
  });

  it('maps tones to default priorities', () => {
    expect(toastPriorityFromTone('danger')).toBe('critical');
    expect(toastPriorityFromTone('warning')).toBe('high');
    expect(toastPriorityFromTone('success')).toBe('low');
    expect(toastPriorityFromTone('info')).toBe('normal');
  });
});
