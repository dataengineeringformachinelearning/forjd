import { isPlatformBrowser } from '@angular/common';
import { DestroyRef, Injectable, PLATFORM_ID, computed, inject, signal } from '@angular/core';

import { getDefaultCommandHistory, type RunHistoryCommand } from '../../core/a11y/command-history';
import { FjToastService } from '../../overlay/toast/toast';

/**
 * Suite command history — ⌘Z / ⌘⇧Z for reversible client actions (ADR-0019).
 * Shares the default stack with forjd-ui helpers and search palette.
 * Shortcuts bind once via `getDefaultCommandHistory()`.
 */
@Injectable({ providedIn: 'root' })
export class FjCommandHistoryService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly destroyRef = inject(DestroyRef);
  private readonly toast = inject(FjToastService);
  private readonly history = getDefaultCommandHistory();
  private readonly version = signal(0);

  readonly canUndo = computed(() => {
    this.version();
    return this.history.canUndo();
  });
  readonly canRedo = computed(() => {
    this.version();
    return this.history.canRedo();
  });
  readonly undoLabel = computed(() => {
    this.version();
    return this.history.undoLabel();
  });
  readonly redoLabel = computed(() => {
    this.version();
    return this.history.redoLabel();
  });

  constructor() {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const unsub = this.history.subscribe(() => {
      this.version.update((n) => n + 1);
    });
    this.destroyRef.onDestroy(() => {
      unsub();
    });
  }

  /** Run a reversible command (records undo only if `do` succeeds). */
  run(command: RunHistoryCommand): Promise<void> {
    return this.history.run(command);
  }

  /**
   * Run a reversible command and offer an Undo toast action.
   * Toast Undo calls the shared stack (same as ⌘Z).
   */
  async runWithUndoToast(
    command: RunHistoryCommand,
    opts?: { readonly description?: string; readonly durationMs?: number },
  ): Promise<void> {
    await this.history.run(command);
    this.toast.show(command.label, {
      description: opts?.description ?? 'Press ⌘Z to undo',
      tone: 'info',
      priority: 'high',
      durationMs: opts?.durationMs ?? 6000,
      action: {
        label: 'Undo',
        onClick: () => {
          void this.undo();
        },
      },
    });
  }

  undo(): Promise<boolean> {
    return this.history.undo();
  }

  redo(): Promise<boolean> {
    return this.history.redo();
  }

  clear(): void {
    this.history.clear();
  }
}
