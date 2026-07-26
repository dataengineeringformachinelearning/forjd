import { afterEach, describe, expect, it, vi } from 'vitest';
import { NativeDialogSession } from './dialog-session';

function stubDialog(dialog: HTMLDialogElement): void {
  let open = false;
  Object.defineProperty(dialog, 'open', {
    get: () => open,
    configurable: true,
  });
  dialog.showModal = () => {
    open = true;
  };
  dialog.close = () => {
    open = false;
    dialog.dispatchEvent(new Event('close'));
  };
}

describe('NativeDialogSession', () => {
  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('opens via showModal and restores focus on close', () => {
    document.body.innerHTML = `
      <button type="button" id="trigger">Open</button>
      <dialog id="dlg"><button type="button" id="inside">Inside</button></dialog>
    `;
    const trigger = document.getElementById('trigger') as HTMLButtonElement;
    const dialog = document.getElementById('dlg') as HTMLDialogElement;
    stubDialog(dialog);
    trigger.focus();

    const session = new NativeDialogSession();
    const closed = vi.fn();

    session.syncOpen(dialog, true);
    expect(dialog.open).toBe(true);

    session.onNativeClose(closed);
    expect(closed).toHaveBeenCalledOnce();
    expect(document.activeElement).toBe(trigger);
  });

  it('ignores backdrop clicks when not dismissible', () => {
    document.body.innerHTML = `<dialog id="dlg"></dialog>`;
    const dialog = document.getElementById('dlg') as HTMLDialogElement;
    stubDialog(dialog);
    dialog.showModal();
    const session = new NativeDialogSession();
    const close = vi.fn();

    const backdropEvent = new MouseEvent('click', { bubbles: true });
    Object.defineProperty(backdropEvent, 'target', {
      value: dialog,
      configurable: true,
    });
    session.onBackdropClick(backdropEvent, dialog, false, close);
    expect(close).not.toHaveBeenCalled();
  });

  it('skips open when host is disconnected', () => {
    document.body.innerHTML = `<dialog id="dlg"></dialog>`;
    const dialog = document.getElementById('dlg') as HTMLDialogElement;
    stubDialog(dialog);
    const session = new NativeDialogSession();
    session.syncOpen(dialog, true, { connected: false });
    expect(dialog.open).toBe(false);
  });
});
