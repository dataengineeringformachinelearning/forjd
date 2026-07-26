/**
 * Multi-select model for list/table bulk actions (ADR-0021).
 * Dual-adapter: keep API aligned with viking-ui/core/selection-model.
 *
 * Keys are stable string ids. Hosts own persistence / server calls;
 * this helper only tracks selection set membership.
 */

export type SelectionModel = {
  readonly selected: () => readonly string[];
  readonly size: () => number;
  readonly isSelected: (id: string) => boolean;
  readonly allSelected: (ids: readonly string[]) => boolean;
  readonly someSelected: (ids: readonly string[]) => boolean;
  toggle: (id: string) => void;
  select: (id: string) => void;
  deselect: (id: string) => void;
  /** Select every id in `ids` (union). */
  selectMany: (ids: readonly string[]) => void;
  /** Select exactly `ids` (replace). */
  setSelected: (ids: readonly string[]) => void;
  /** Toggle all: if every id selected → clear those; else select all. */
  toggleAll: (ids: readonly string[]) => void;
  clear: () => void;
  /** Drop ids that are no longer in the visible/page set. */
  pruneTo: (ids: readonly string[]) => void;
  subscribe: (listener: () => void) => () => void;
};

export type CreateSelectionModelOptions = {
  readonly initial?: readonly string[];
  readonly maxSelected?: number;
};

export function createSelectionModel(options?: CreateSelectionModelOptions): SelectionModel {
  const maxSelected = options?.maxSelected;
  const selected = new Set<string>((options?.initial ?? []).map(String).filter(Boolean));
  const listeners = new Set<() => void>();

  const notify = (): void => {
    for (const listener of listeners) {
      try {
        listener();
      } catch {
        // Listener failures must not break selection.
      }
    }
  };

  const enforceCap = (): void => {
    if (maxSelected == null || selected.size <= maxSelected) {
      return;
    }
    const keep = [...selected].slice(0, maxSelected);
    selected.clear();
    for (const id of keep) {
      selected.add(id);
    }
  };

  return {
    selected: () => [...selected],
    size: () => selected.size,
    isSelected: (id) => selected.has(String(id)),
    allSelected: (ids) => {
      if (!ids.length) {
        return false;
      }
      return ids.every((id) => selected.has(String(id)));
    },
    someSelected: (ids) => {
      if (!ids.length) {
        return false;
      }
      const hits = ids.filter((id) => selected.has(String(id))).length;
      return hits > 0 && hits < ids.length;
    },
    toggle: (id) => {
      const key = String(id);
      if (!key) {
        return;
      }
      if (selected.has(key)) {
        selected.delete(key);
      } else {
        selected.add(key);
        enforceCap();
      }
      notify();
    },
    select: (id) => {
      const key = String(id);
      if (!key || selected.has(key)) {
        return;
      }
      selected.add(key);
      enforceCap();
      notify();
    },
    deselect: (id) => {
      if (selected.delete(String(id))) {
        notify();
      }
    },
    selectMany: (ids) => {
      let changed = false;
      for (const id of ids) {
        const key = String(id);
        if (!key || selected.has(key)) {
          continue;
        }
        selected.add(key);
        changed = true;
      }
      if (changed) {
        enforceCap();
        notify();
      }
    },
    setSelected: (ids) => {
      selected.clear();
      for (const id of ids) {
        const key = String(id);
        if (key) {
          selected.add(key);
        }
      }
      enforceCap();
      notify();
    },
    toggleAll: (ids) => {
      const keys = ids.map(String).filter(Boolean);
      if (!keys.length) {
        return;
      }
      const allOn = keys.every((id) => selected.has(id));
      if (allOn) {
        for (const id of keys) {
          selected.delete(id);
        }
      } else {
        for (const id of keys) {
          selected.add(id);
        }
        enforceCap();
      }
      notify();
    },
    clear: () => {
      if (!selected.size) {
        return;
      }
      selected.clear();
      notify();
    },
    pruneTo: (ids) => {
      const allow = new Set(ids.map(String));
      let changed = false;
      for (const id of [...selected]) {
        if (!allow.has(id)) {
          selected.delete(id);
          changed = true;
        }
      }
      if (changed) {
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
