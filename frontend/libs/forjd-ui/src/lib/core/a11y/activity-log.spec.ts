import { createActivityLog, resetDefaultActivityLog } from './activity-log';

describe('createActivityLog', () => {
  afterEach(() => {
    resetDefaultActivityLog();
  });

  it('records newest-first and caps length', () => {
    const log = createActivityLog({ storage: null, maxEntries: 3 });
    log.record({ kind: 'a', label: 'One' });
    log.record({ kind: 'b', label: 'Two' });
    log.record({ kind: 'c', label: 'Three' });
    log.record({ kind: 'd', label: 'Four' });
    expect(log.list().map((e) => e.label)).toEqual(['Four', 'Three', 'Two']);
  });

  it('rejects sensitive labels', () => {
    const log = createActivityLog({ storage: null });
    const entry = log.record({
      kind: 'preferences.export',
      label: 'Exported fjsvc_abc123token',
    });
    expect(entry).toBeNull();
    expect(log.list()).toHaveLength(0);
  });

  it('notifies subscribers and clears', () => {
    const log = createActivityLog({ storage: null });
    let ticks = 0;
    log.subscribe(() => {
      ticks += 1;
    });
    log.record({ kind: 'disclosure.reset', label: 'Reset advanced sections' });
    expect(ticks).toBe(1);
    log.clear();
    expect(ticks).toBe(2);
    expect(log.list()).toHaveLength(0);
  });

  it('persists to storage and rejects JWT-like labels', () => {
    const memory = new Map<string, string>();
    const storage = {
      getItem: (k: string) => memory.get(k) ?? null,
      setItem: (k: string, v: string) => {
        memory.set(k, v);
      },
      removeItem: (k: string) => {
        memory.delete(k);
      },
    };
    const log = createActivityLog({ storage, maxEntries: 10 });
    log.record({
      kind: 'preferences.export',
      label: 'Exported local preferences',
      source: 'forjd',
    });
    expect(memory.get('suite-activity-v1')).toContain('preferences.export');
    expect(
      log.record({
        kind: 'leak',
        label: 'token eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig',
      }),
    ).toBeNull();
  });
});
