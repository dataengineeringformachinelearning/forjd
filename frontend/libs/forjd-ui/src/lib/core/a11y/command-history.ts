/**
 * Undo/redo stack for reversible client actions (ADR-0019).
 * Dual-adapter: keep API aligned with viking-ui/core/command-history.
 *
 * Use for local UI mutations (theme, recent searches, soft client state).
 * Do not invent server soft-delete here — irreversible API deletes stay confirm-only.
 */

export type HistoryEntry = {
  readonly id: string;
  readonly label: string;
  readonly undo: () => void | Promise<void>;
  readonly redo: () => void | Promise<void>;
};

export type RunHistoryCommand = {
  readonly label: string;
  /** Forward action — runs immediately; history records only on success. */
  readonly do: () => void | Promise<void>;
  /** Inverse — restores prior state. */
  readonly undo: () => void | Promise<void>;
  readonly id?: string;
};

export type CommandHistory = {
  run: (command: RunHistoryCommand) => Promise<void>;
  undo: () => Promise<boolean>;
  redo: () => Promise<boolean>;
  clear: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;
  undoLabel: () => string | null;
  redoLabel: () => string | null;
  subscribe: (listener: () => void) => () => void;
};

export type CreateCommandHistoryOptions = {
  readonly maxDepth?: number;
};

const DEFAULT_MAX_DEPTH = 40;

let defaultHistory: CommandHistory | null = null;
let defaultUnbindShortcuts: (() => void) | null = null;
let historySeq = 0;

/** Shared suite history so Angular hosts and optional WC callers share one stack. */
export function getDefaultCommandHistory(options?: CreateCommandHistoryOptions): CommandHistory {
  if (!defaultHistory) {
    defaultHistory = createCommandHistory(options);
    // One global shortcut binding for the shared stack (avoid double ⌘Z).
    if (typeof document !== 'undefined') {
      defaultUnbindShortcuts = bindCommandHistoryShortcuts(defaultHistory);
    }
  }
  return defaultHistory;
}

/** @internal test helper — reset the shared singleton. */
export function resetDefaultCommandHistoryForTests(): void {
  defaultUnbindShortcuts?.();
  defaultUnbindShortcuts = null;
  defaultHistory = null;
}

export function createCommandHistory(options?: CreateCommandHistoryOptions): CommandHistory {
  const maxDepth = Math.max(1, options?.maxDepth ?? DEFAULT_MAX_DEPTH);
  const undoStack: HistoryEntry[] = [];
  const redoStack: HistoryEntry[] = [];
  const listeners = new Set<() => void>();
  let busy = false;

  const notify = (): void => {
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        // Listener failures must not break the stack.
      }
    }
  };

  const pushUndo = (entry: HistoryEntry): void => {
    undoStack.push(entry);
    while (undoStack.length > maxDepth) {
      undoStack.shift();
    }
    redoStack.length = 0;
    notify();
  };

  return {
    async run(command) {
      if (busy) {
        return;
      }
      busy = true;
      try {
        await command.do();
        pushUndo({
          id: command.id ?? `cmd-${++historySeq}`,
          label: command.label.trim() || 'Action',
          undo: command.undo,
          redo: command.do,
        });
      } finally {
        busy = false;
      }
    },

    async undo() {
      if (busy || undoStack.length === 0) {
        return false;
      }
      busy = true;
      const entry = undoStack.pop()!;
      try {
        await entry.undo();
        redoStack.push(entry);
        notify();
        return true;
      } catch {
        undoStack.push(entry);
        notify();
        return false;
      } finally {
        busy = false;
      }
    },

    async redo() {
      if (busy || redoStack.length === 0) {
        return false;
      }
      busy = true;
      const entry = redoStack.pop()!;
      try {
        await entry.redo();
        undoStack.push(entry);
        while (undoStack.length > maxDepth) {
          undoStack.shift();
        }
        notify();
        return true;
      } catch {
        redoStack.push(entry);
        notify();
        return false;
      } finally {
        busy = false;
      }
    },

    clear() {
      undoStack.length = 0;
      redoStack.length = 0;
      notify();
    },

    canUndo: () => undoStack.length > 0,
    canRedo: () => redoStack.length > 0,
    undoLabel: () => undoStack[undoStack.length - 1]?.label ?? null,
    redoLabel: () => redoStack[redoStack.length - 1]?.label ?? null,

    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName;
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    return true;
  }
  if (target.isContentEditable) {
    return true;
  }
  return Boolean(target.closest("[contenteditable='true']"));
}

/**
 * Bind ⌘Z / Ctrl+Z (undo) and ⌘⇧Z / Ctrl+Y (redo).
 * Skips when focus is in an editable field.
 */
export function bindCommandHistoryShortcuts(
  history: CommandHistory,
  options?: { readonly target?: Document },
): () => void {
  const doc = options?.target ?? (typeof document !== 'undefined' ? document : null);
  if (!doc) {
    return () => undefined;
  }

  const onKeydown = (event: KeyboardEvent): void => {
    if (!event.metaKey && !event.ctrlKey) {
      return;
    }
    if (isEditableTarget(event.target)) {
      return;
    }
    const key = event.key.toLowerCase();
    const shiftRedo = key === 'z' && event.shiftKey;
    const yankRedo = key === 'y' && !event.shiftKey;
    if (key === 'z' && !event.shiftKey) {
      if (!history.canUndo()) {
        return;
      }
      event.preventDefault();
      void history.undo();
      return;
    }
    if (shiftRedo || yankRedo) {
      if (!history.canRedo()) {
        return;
      }
      event.preventDefault();
      void history.redo();
    }
  };

  doc.addEventListener('keydown', onKeydown);
  return () => doc.removeEventListener('keydown', onKeydown);
}
