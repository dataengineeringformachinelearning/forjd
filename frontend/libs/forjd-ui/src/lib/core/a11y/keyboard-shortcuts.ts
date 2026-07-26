/**
 * Suite keyboard shortcut registry + helpers (ADR-0023).
 * Dual-adapter: keep API aligned with viking-ui/core/keyboard-shortcuts.
 *
 * Features keep their own listeners (search, undo); this catalog documents
 * them and owns the help chord (`?`). Never store secrets in shortcut state.
 */

export type SuiteShortcut = {
  readonly id: string;
  /**
   * Display chord tokens. Use `Mod` for ⌘ (macOS) / Ctrl (elsewhere).
   * Examples: `['Mod', 'K']`, `['/']`, `['?']`, `['Esc']`.
   */
  readonly keys: readonly string[];
  readonly label: string;
  readonly group: string;
  readonly description?: string;
};

export type ShortcutRegistry = {
  readonly list: () => readonly SuiteShortcut[];
  readonly byGroup: () => ReadonlyArray<{
    readonly group: string;
    readonly items: readonly SuiteShortcut[];
  }>;
  readonly register: (shortcut: SuiteShortcut) => void;
  readonly unregister: (id: string) => void;
  readonly subscribe: (listener: () => void) => () => void;
};

export type CreateShortcutRegistryOptions = {
  readonly initial?: readonly SuiteShortcut[];
};

/** True when keydown should not steal typing focus. */
export function isEditableKeyboardTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  if (target.isContentEditable) {
    return true;
  }
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    return true;
  }
  return Boolean(target.closest('[contenteditable="true"], [role="textbox"]'));
}

export function prefersMacModKey(
  platform: string = typeof navigator !== 'undefined' ? navigator.platform : '',
): boolean {
  return /Mac|iPhone|iPad/i.test(platform);
}

/** Expand `Mod` and join for docs / aria. */
export function formatShortcutChord(
  keys: readonly string[],
  options?: { readonly mac?: boolean },
): string {
  const mac = options?.mac ?? prefersMacModKey();
  return keys
    .map((token) => {
      if (token === 'Mod') {
        return mac ? '⌘' : 'Ctrl';
      }
      if (token === 'Shift') {
        return mac ? '⇧' : 'Shift';
      }
      if (token === 'Alt') {
        return mac ? '⌥' : 'Alt';
      }
      return token;
    })
    .join(mac ? '' : '+');
}

/** Built-in suite shortcuts (search / undo / help). Bindings live with owners. */
export function suiteDefaultShortcuts(): readonly SuiteShortcut[] {
  return [
    {
      id: 'search',
      keys: ['Mod', 'K'],
      label: 'Open search',
      group: 'Navigation',
      description: 'Command palette — jump to docs and destinations.',
    },
    {
      id: 'search-slash',
      keys: ['/'],
      label: 'Open search',
      group: 'Navigation',
      description: 'Same as Mod+K when focus is not in a field.',
    },
    {
      id: 'close-overlay',
      keys: ['Esc'],
      label: 'Close overlay',
      group: 'Navigation',
      description: 'Dismiss search, dialogs, sheets, and shortcut help.',
    },
    {
      id: 'preferences',
      keys: ['Mod', ','],
      label: 'Open preferences',
      group: 'Navigation',
      description: 'Appearance and local UI preferences (ADR-0024).',
    },
    {
      id: 'undo',
      keys: ['Mod', 'Z'],
      label: 'Undo',
      group: 'Editing',
      description: 'Reversible client actions only (ADR-0019).',
    },
    {
      id: 'redo',
      keys: ['Mod', 'Shift', 'Z'],
      label: 'Redo',
      group: 'Editing',
    },
    {
      id: 'redo-y',
      keys: ['Mod', 'Y'],
      label: 'Redo',
      group: 'Editing',
      description: 'Windows / Linux alternate.',
    },
    {
      id: 'shortcut-help',
      keys: ['?'],
      label: 'Keyboard shortcuts',
      group: 'Help',
      description: 'Open this reference.',
    },
  ];
}

export function createShortcutRegistry(options?: CreateShortcutRegistryOptions): ShortcutRegistry {
  const byId = new Map<string, SuiteShortcut>();
  for (const item of options?.initial ?? []) {
    byId.set(item.id, item);
  }
  const listeners = new Set<() => void>();

  const notify = (): void => {
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        // Listener failures must not break shortcuts.
      }
    }
  };

  return {
    list: () => [...byId.values()],
    byGroup: () => {
      const groups = new Map<string, SuiteShortcut[]>();
      for (const item of byId.values()) {
        const bucket = groups.get(item.group) ?? [];
        bucket.push(item);
        groups.set(item.group, bucket);
      }
      return [...groups.entries()].map(([group, items]) => ({ group, items }));
    },
    register: (shortcut) => {
      const id = String(shortcut.id).slice(0, 64);
      if (!id) {
        return;
      }
      byId.set(id, { ...shortcut, id });
      notify();
    },
    unregister: (id) => {
      if (byId.delete(String(id))) {
        notify();
      }
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

let defaultRegistry: ShortcutRegistry | null = null;

export function getDefaultShortcutRegistry(): ShortcutRegistry {
  if (!defaultRegistry) {
    defaultRegistry = createShortcutRegistry({
      initial: suiteDefaultShortcuts(),
    });
  }
  return defaultRegistry;
}

export function resetDefaultShortcutRegistry(): void {
  defaultRegistry = null;
}

/**
 * Bind `?` (Shift+/) to open shortcut help.
 * Skips editable fields and when a modifier other than Shift is held.
 */
export function bindShortcutHelpKey(
  onOpen: () => void,
  options?: { readonly target?: Document },
): () => void {
  const doc = options?.target ?? (typeof document !== 'undefined' ? document : null);
  if (!doc) {
    return () => undefined;
  }

  const onKeydown = (event: KeyboardEvent): void => {
    if (event.defaultPrevented) {
      return;
    }
    if (event.metaKey || event.ctrlKey || event.altKey) {
      return;
    }
    if (event.key !== '?') {
      return;
    }
    if (isEditableKeyboardTarget(event.target)) {
      return;
    }
    event.preventDefault();
    onOpen();
  };

  doc.addEventListener('keydown', onKeydown);
  return () => doc.removeEventListener('keydown', onKeydown);
}
