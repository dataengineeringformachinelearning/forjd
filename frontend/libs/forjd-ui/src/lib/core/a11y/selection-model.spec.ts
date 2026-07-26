import { createSelectionModel } from './selection-model';

describe('createSelectionModel', () => {
  it('toggles, select-all, and clears', () => {
    const model = createSelectionModel();
    model.toggle('a');
    model.toggle('b');
    expect(model.selected()).toEqual(['a', 'b']);
    expect(model.someSelected(['a', 'b', 'c'])).toBe(true);
    expect(model.allSelected(['a', 'b'])).toBe(true);

    model.toggleAll(['a', 'b', 'c']);
    expect(model.allSelected(['a', 'b', 'c'])).toBe(true);

    model.toggleAll(['a', 'b', 'c']);
    expect(model.size()).toBe(0);
  });

  it('prunes stale ids and enforces maxSelected', () => {
    const model = createSelectionModel({ maxSelected: 2 });
    model.selectMany(['a', 'b', 'c']);
    expect(model.size()).toBe(2);
    model.pruneTo(['b']);
    expect(model.selected()).toEqual(['b']);
  });
});
