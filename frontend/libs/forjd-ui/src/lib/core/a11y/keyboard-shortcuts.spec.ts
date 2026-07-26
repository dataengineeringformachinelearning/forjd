import {
  bindShortcutHelpKey,
  createShortcutRegistry,
  formatShortcutChord,
  isEditableKeyboardTarget,
  resetDefaultShortcutRegistry,
  suiteDefaultShortcuts,
} from './keyboard-shortcuts';

describe('keyboard shortcuts', () => {
  afterEach(() => {
    resetDefaultShortcutRegistry();
  });

  it('formats Mod for mac and non-mac', () => {
    expect(formatShortcutChord(['Mod', 'K'], { mac: true })).toBe('⌘K');
    expect(formatShortcutChord(['Mod', 'K'], { mac: false })).toBe('Ctrl+K');
  });

  it('groups registered shortcuts', () => {
    const registry = createShortcutRegistry({
      initial: suiteDefaultShortcuts(),
    });
    const groups = registry.byGroup();
    expect(groups.some((g) => g.group === 'Navigation')).toBe(true);
    expect(groups.some((g) => g.group === 'Help')).toBe(true);
  });

  it('detects editable targets', () => {
    const input = document.createElement('input');
    expect(isEditableKeyboardTarget(input)).toBe(true);
    expect(isEditableKeyboardTarget(document.createElement('div'))).toBe(false);
  });

  it('binds ? outside editable fields', () => {
    let opened = 0;
    const unbind = bindShortcutHelpKey(() => {
      opened += 1;
    });
    document.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true }));
    expect(opened).toBe(1);

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.dispatchEvent(new KeyboardEvent('keydown', { key: '?', bubbles: true }));
    expect(opened).toBe(1);
    input.remove();
    unbind();
  });
});
