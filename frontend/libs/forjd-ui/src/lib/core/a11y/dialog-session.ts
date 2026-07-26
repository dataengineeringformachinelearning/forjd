/**
 * Native <dialog> focus session — shared by dialog/sheet (and viking modal/sheet).
 * Captures return focus, opens via showModal, traps Tab, restores on close.
 */

import { captureReturnFocus, focusFirst, restoreFocus, trapTabKey } from './focus';

/** Stateful helper for one native dialog host at a time. */
export class NativeDialogSession {
  private returnFocus: HTMLElement | null = null;

  /**
   * Sync `open` model → dialog.showModal() / close().
   * Pass `connected: false` when the host is detached (SSR / destroy).
   */
  syncOpen(dialog: HTMLDialogElement, wantOpen: boolean, options?: { connected?: boolean }): void {
    if (typeof dialog.showModal !== 'function') return;
    const connected = options?.connected !== false;
    if (wantOpen && connected && !dialog.open) {
      this.returnFocus = captureReturnFocus();
      dialog.showModal();
      queueMicrotask(() => focusFirst(dialog));
    } else if (!wantOpen && dialog.open) {
      dialog.close();
    }
  }

  /** Native `close` event — clear model + restore focus. */
  onNativeClose(setClosed: () => void): void {
    setClosed();
    restoreFocus(this.returnFocus);
    this.returnFocus = null;
  }

  /** Backdrop click on the dialog element itself. */
  onBackdropClick(
    event: MouseEvent,
    dialog: HTMLDialogElement,
    dismissible: boolean,
    close: () => void,
  ): void {
    if (!dismissible) return;
    if (event.target === dialog) close();
  }

  /** Defensive Tab trap (complements native modal focus retention). */
  onKeydown(event: KeyboardEvent, dialog: HTMLDialogElement): void {
    trapTabKey(event, dialog);
  }

  /** Close on destroy if still open. */
  destroy(dialog: HTMLDialogElement | null | undefined): void {
    if (dialog?.open) dialog.close();
  }
}
