import {
  bindCommandHistoryShortcuts,
  createCommandHistory,
  resetDefaultCommandHistoryForTests,
} from './command-history';

describe('createCommandHistory', () => {
  afterEach(() => {
    resetDefaultCommandHistoryForTests();
  });

  it('runs, undoes, and redoes in order', async () => {
    const values: number[] = [];
    const history = createCommandHistory();

    await history.run({
      label: 'Add 1',
      do: () => {
        values.push(1);
      },
      undo: () => {
        values.pop();
      },
    });
    await history.run({
      label: 'Add 2',
      do: () => {
        values.push(2);
      },
      undo: () => {
        values.pop();
      },
    });

    expect(values).toEqual([1, 2]);
    expect(history.undoLabel()).toBe('Add 2');

    await history.undo();
    expect(values).toEqual([1]);
    expect(history.canRedo()).toBe(true);

    await history.redo();
    expect(values).toEqual([1, 2]);
  });

  it('does not record history when do throws', async () => {
    const history = createCommandHistory();
    await expect(
      history.run({
        label: 'Fail',
        do: () => {
          throw new Error('boom');
        },
        undo: () => undefined,
      }),
    ).rejects.toThrow('boom');
    expect(history.canUndo()).toBe(false);
  });

  it('binds keyboard shortcuts outside editable fields', async () => {
    const history = createCommandHistory();
    let n = 0;
    await history.run({
      label: 'Inc',
      do: () => {
        n += 1;
      },
      undo: () => {
        n -= 1;
      },
    });
    const unbind = bindCommandHistoryShortcuts(history);
    document.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'z',
        metaKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );
    await Promise.resolve();
    expect(n).toBe(0);
    unbind();
  });
});
