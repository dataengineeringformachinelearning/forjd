import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';

import {
  formatShortcutChord,
  prefersMacModKey,
  type SuiteShortcut,
} from '../../core/a11y/keyboard-shortcuts';
import { FjShortcutHelpService } from '../../chrome/shortcuts/shortcut-help.service';
import { FjDialog } from '../dialog/dialog';

/**
 * Keyboard shortcut reference dialog (ADR-0023).
 * Open via `?` or `FjShortcutHelpService.show()`.
 */
@Component({
  selector: 'forjd-shortcut-help',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjDialog],
  template: `
    <forjd-dialog
      [open]="help.open()"
      (openChange)="help.setOpen($event)"
      title="Keyboard shortcuts"
    >
      <div class="suite-shortcut-help fj-shortcut-help viking-shortcut-help">
        <p class="suite-shortcut-help-lede fj-shortcut-help-lede viking-shortcut-help-lede">
          Power-user chords for FORJD / DEML suite chrome. Press
          <span class="suite-kbd fj-kbd viking-kbd">?</span> anytime (outside fields).
        </p>
        @for (group of groups(); track group.group) {
          <section
            class="suite-shortcut-help-group fj-shortcut-help-group viking-shortcut-help-group"
            [attr.aria-label]="group.group"
          >
            <h3
              class="suite-shortcut-help-group-title fj-shortcut-help-group-title viking-shortcut-help-group-title"
            >
              {{ group.group }}
            </h3>
            <ul class="suite-shortcut-help-list fj-shortcut-help-list viking-shortcut-help-list">
              @for (item of group.items; track item.id) {
                <li>
                  <div
                    class="suite-shortcut-help-row fj-shortcut-help-row viking-shortcut-help-row"
                  >
                    <div>
                      <p
                        class="suite-shortcut-help-label fj-shortcut-help-label viking-shortcut-help-label"
                      >
                        {{ item.label }}
                      </p>
                      @if (item.description) {
                        <p
                          class="suite-shortcut-help-desc fj-shortcut-help-desc viking-shortcut-help-desc"
                        >
                          {{ item.description }}
                        </p>
                      }
                    </div>
                    <div
                      class="suite-shortcut-help-keys fj-shortcut-help-keys viking-shortcut-help-keys"
                      [attr.aria-label]="chord(item)"
                    >
                      @for (token of displayKeys(item); track $index) {
                        <span class="suite-kbd fj-kbd viking-kbd">{{ token }}</span>
                      }
                    </div>
                  </div>
                </li>
              }
            </ul>
          </section>
        }
      </div>
    </forjd-dialog>
  `,
  styles: [
    `
      :host {
        display: contents;
      }
    `,
  ],
})
export class FjShortcutHelp {
  protected readonly help = inject(FjShortcutHelpService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly mac = prefersMacModKey();
  private readonly tick = signal(0);

  constructor() {
    const unsub = this.help.registry.subscribe(() => this.tick.update((n) => n + 1));
    this.destroyRef.onDestroy(unsub);
  }

  protected readonly groups = computed(() => {
    this.tick();
    return this.help.registry.byGroup();
  });

  protected displayKeys(item: SuiteShortcut): string[] {
    return item.keys.map((token) => {
      if (token === 'Mod') {
        return this.mac ? '⌘' : 'Ctrl';
      }
      if (token === 'Shift') {
        return this.mac ? '⇧' : 'Shift';
      }
      if (token === 'Alt') {
        return this.mac ? '⌥' : 'Alt';
      }
      return token;
    });
  }

  protected chord(item: SuiteShortcut): string {
    return formatShortcutChord(item.keys, { mac: this.mac });
  }
}
