import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  OnDestroy,
  PLATFORM_ID,
  computed,
  effect,
  inject,
  input,
  model,
  output,
  signal,
  viewChild,
} from '@angular/core';

import { NativeDialogSession } from '../../core/a11y/dialog-session';
import { forjdUid } from '../../core/a11y/uid';
import { sanitizeDisplayText } from '../../core/a11y/sanitize-text';
import { FjCommandHistoryService } from '../../chrome/history/command-history.service';
import { rankSearchItems } from './rank-search';
import {
  DEFAULT_RECENT_STORAGE_KEY,
  clearRecentSearches,
  pushRecentSearch,
  readRecentSearches,
  recentSearchesAsItems,
  restoreRecentSearches,
} from './recent-searches';
import type { FjSearchPaletteItem } from './search-palette.types';

export type { FjSearchPaletteItem } from './search-palette.types';

const RECENT_HREF_PREFIX = '#fj-recent:';

type ResultGroup = { readonly group: string; readonly items: FjSearchPaletteItem[] };

function groupItems(items: readonly FjSearchPaletteItem[]): ResultGroup[] {
  const order: string[] = [];
  const map = new Map<string, FjSearchPaletteItem[]>();
  for (const item of items) {
    const group = item.group?.trim() || '';
    if (!map.has(group)) {
      map.set(group, []);
      order.push(group);
    }
    map.get(group)!.push(item);
  }
  return order.map((group) => ({ group, items: map.get(group)! }));
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

function modKeyLabel(): string {
  if (typeof navigator === 'undefined') {
    return 'Ctrl';
  }
  return /Mac|iPhone|iPad/i.test(navigator.platform) ? '⌘' : 'Ctrl';
}

// --- Suite command palette (⌘K · / · recent searches) ---
@Component({
  selector: 'forjd-search-palette',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dialog
      #dialog
      class="suite-search-palette-backdrop fj-search-palette-backdrop viking-search-palette-backdrop"
      aria-labelledby="fj-search-palette-label"
      (close)="onNativeClose()"
      (click)="onBackdrop($event)"
      (keydown)="onDialogKeydown($event)"
    >
      <div
        class="suite-search-palette fj-search-palette viking-search-palette"
        role="presentation"
        (click)="$event.stopPropagation()"
      >
        <header
          class="suite-search-palette-header fj-search-palette-header viking-search-palette-header"
        >
          <span class="visually-hidden" id="fj-search-palette-label">Search</span>
          <input
            #queryInput
            type="search"
            class="suite-search-palette-input fj-search-palette-input viking-search-palette-input"
            [id]="inputId"
            [attr.aria-controls]="resultsId"
            [attr.aria-activedescendant]="activeDescendant()"
            [attr.aria-label]="placeholder()"
            [placeholder]="placeholder()"
            autocomplete="off"
            spellcheck="false"
            [value]="query()"
            (input)="onQueryInput($event)"
            (keydown)="onInputKeydown($event)"
          />
          <button
            type="button"
            class="suite-search-palette-close fj-search-palette-close viking-search-palette-close"
            aria-label="Close search"
            (click)="open.set(false)"
          >
            Esc
          </button>
        </header>
        <div
          class="suite-search-palette-body fj-search-palette-body viking-search-palette-body"
          [id]="resultsId"
        >
          @if (flatResults().length === 0) {
            <p class="suite-search-empty fj-search-empty viking-search-empty" role="status">
              {{ query().trim() ? 'No results found' : 'Start typing to search…' }}
            </p>
          } @else {
            <div
              class="suite-search-results fj-search-results viking-search-results"
              role="listbox"
              aria-label="Search results"
            >
              @for (group of groupedResults(); track group.group + $index) {
                @if (group.group) {
                  <div
                    class="suite-search-group-header fj-search-group-header viking-search-group-header"
                    role="presentation"
                  >
                    <p
                      class="suite-search-group-label fj-search-group-label viking-search-group-label"
                    >
                      {{ group.group }}
                    </p>
                    @if (group.group === 'Recent') {
                      <button
                        type="button"
                        class="suite-search-clear-recent fj-search-clear-recent viking-search-clear-recent"
                        (click)="clearRecent()"
                      >
                        Clear recent
                      </button>
                    }
                  </div>
                }
                @for (item of group.items; track item.href + item.title; let i = $index) {
                  <a
                    class="suite-search-result fj-search-result viking-search-result"
                    role="option"
                    [id]="resultId(flatIndex(group, i))"
                    [class.is-selected]="flatIndex(group, i) === activeIndex()"
                    [attr.aria-selected]="flatIndex(group, i) === activeIndex()"
                    [href]="item.href"
                    (click)="onResultClick($event, item)"
                    (mouseenter)="activeIndex.set(flatIndex(group, i))"
                  >
                    <div>
                      <div
                        class="suite-search-result-title fj-search-result-title viking-search-result-title"
                      >
                        {{ item.title }}
                      </div>
                      @if (item.snippet) {
                        <div
                          class="suite-search-result-snippet fj-search-result-snippet viking-search-result-snippet"
                        >
                          {{ item.snippet }}
                        </div>
                      }
                    </div>
                  </a>
                }
              }
            </div>
          }
        </div>
        <footer
          class="suite-search-palette-footer fj-search-palette-footer viking-search-palette-footer"
        >
          <span class="suite-kbd fj-kbd viking-kbd">{{ modKey }}</span
          ><span class="suite-kbd fj-kbd viking-kbd">K</span> /
          <span class="suite-kbd fj-kbd viking-kbd">/</span> open ·
          <span class="suite-kbd fj-kbd viking-kbd">↑</span
          ><span class="suite-kbd fj-kbd viking-kbd">↓</span> navigate ·
          <span class="suite-kbd fj-kbd viking-kbd">Enter</span> open ·
          <span class="suite-kbd fj-kbd viking-kbd">Esc</span> close ·
          <span class="suite-kbd fj-kbd viking-kbd">?</span> all shortcuts
        </footer>
      </div>
    </dialog>
  `,
  styles: [
    `
      :host {
        display: contents;
      }
      .visually-hidden {
        position: absolute;
        width: 1px;
        height: 1px;
        padding: 0;
        margin: -1px;
        overflow: hidden;
        clip: rect(0, 0, 0, 0);
        white-space: nowrap;
        border: 0;
      }
    `,
  ],
})
/**
 * Suite command palette (⌘K / `/`). Soft chrome only — see COMPONENTS.md.
 */
export class FjSearchPalette implements OnDestroy {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly destroyRef = inject(DestroyRef);
  private readonly history = inject(FjCommandHistoryService);
  private readonly session = new NativeDialogSession();

  /** Two-way open state (`[(open)]`). */
  readonly open = model(false);
  /** Curated destinations (ranked + merged with local recents). */
  readonly items = input<readonly FjSearchPaletteItem[]>([]);
  readonly placeholder = input('Search documentation, API, and product…');
  /** When true, document-level ⌘K and `/` open the palette. */
  readonly globalShortcut = input(true);
  /** localStorage key for recent searches (never secrets). */
  readonly recentStorageKey = input(DEFAULT_RECENT_STORAGE_KEY);

  readonly queryChange = output<string>();
  /** Fired when the user activates a result (click / Enter). */
  readonly select = output<FjSearchPaletteItem>();

  protected readonly query = signal('');
  protected readonly activeIndex = signal(0);
  protected readonly recentTick = signal(0);
  protected readonly inputId = forjdUid('fj-search-input');
  protected readonly resultsId = forjdUid('fj-search-results');
  protected readonly modKey = modKeyLabel();

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private readonly queryInput = viewChild<ElementRef<HTMLInputElement>>('queryInput');

  private globalKeyHandler: ((event: KeyboardEvent) => void) | null = null;

  protected readonly flatResults = computed(() => {
    this.recentTick();
    const curated = this.items();
    const q = this.query().trim();
    if (q) {
      return rankSearchItems(curated, q);
    }
    const recent = recentSearchesAsItems(readRecentSearches(this.recentStorageKey())).map(
      (item) => ({
        ...item,
        title: sanitizeDisplayText(item.title),
        snippet: item.snippet ? sanitizeDisplayText(item.snippet) : undefined,
      }),
    );
    const seen = new Set(recent.map((item) => `${item.title}:${item.href}`));
    const rest = curated.filter((item) => {
      const key = `${item.title}:${item.href}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
    return [...recent, ...rest];
  });

  protected readonly groupedResults = computed(() => groupItems(this.flatResults()));

  protected readonly activeDescendant = computed(() => {
    const flat = this.flatResults();
    if (!flat.length) {
      return null;
    }
    const idx = Math.min(this.activeIndex(), flat.length - 1);
    return this.resultId(idx);
  });

  constructor() {
    effect(() => {
      this.session.syncOpen(this.dialog().nativeElement, this.open());
      if (this.open()) {
        queueMicrotask(() => this.queryInput()?.nativeElement.focus());
      }
    });

    effect(() => {
      if (!isPlatformBrowser(this.platformId)) {
        return;
      }
      this.unbindGlobalShortcut();
      if (this.globalShortcut()) {
        this.bindGlobalShortcut();
      }
    });

    this.destroyRef.onDestroy(() => this.unbindGlobalShortcut());
  }

  ngOnDestroy(): void {
    this.session.destroy(this.dialog()?.nativeElement);
    this.unbindGlobalShortcut();
  }

  /** Opens the palette. */
  openPalette(): void {
    this.open.set(true);
  }

  /** Closes the palette and clears the query. */
  closePalette(): void {
    this.open.set(false);
    this.query.set('');
    this.activeIndex.set(0);
  }

  /** Sets the query and refreshes ranked results. */
  search(next: string): void {
    this.query.set(next);
    this.activeIndex.set(0);
    this.queryChange.emit(next);
  }

  protected flatIndex(group: ResultGroup, localIndex: number): number {
    let offset = 0;
    for (const g of this.groupedResults()) {
      if (g === group) {
        return offset + localIndex;
      }
      offset += g.items.length;
    }
    return localIndex;
  }

  protected resultId(index: number): string {
    return `${this.resultsId}-result-${index}`;
  }

  protected onQueryInput(event: Event): void {
    const next = (event.target as HTMLInputElement).value;
    this.search(next);
  }

  protected onInputKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.closePalette();
      return;
    }
    const flat = this.flatResults();
    if (!flat.length) {
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      this.activeIndex.set(Math.min(flat.length - 1, this.activeIndex() + 1));
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      this.activeIndex.set(Math.max(0, this.activeIndex() - 1));
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const item = flat[this.activeIndex()];
      if (item) {
        this.activateItem(item);
      }
    }
  }

  protected onResultClick(event: MouseEvent, item: FjSearchPaletteItem): void {
    event.preventDefault();
    this.activateItem(item);
  }

  protected clearRecent(): void {
    const key = this.recentStorageKey();
    const snapshot = readRecentSearches(key);
    if (!snapshot.length) {
      return;
    }
    void this.history.runWithUndoToast({
      label: 'Cleared recent searches',
      do: () => {
        clearRecentSearches(key);
        this.recentTick.update((n) => n + 1);
      },
      undo: () => {
        restoreRecentSearches(snapshot, key);
        this.recentTick.update((n) => n + 1);
      },
    });
  }

  protected onNativeClose(): void {
    this.session.onNativeClose(() => {
      if (this.open()) {
        this.open.set(false);
      }
      this.query.set('');
      this.activeIndex.set(0);
    });
  }

  protected onBackdrop(event: MouseEvent): void {
    this.session.onBackdropClick(event, this.dialog().nativeElement, true, () =>
      this.closePalette(),
    );
  }

  protected onDialogKeydown(event: KeyboardEvent): void {
    this.session.onKeydown(event, this.dialog().nativeElement);
  }

  private activateItem(item: FjSearchPaletteItem): void {
    if (item.href.startsWith(RECENT_HREF_PREFIX)) {
      const encoded = item.href.slice(RECENT_HREF_PREFIX.length);
      let next = item.title;
      try {
        next = decodeURIComponent(encoded) || item.title;
      } catch {
        next = item.title;
      }
      this.search(next);
      return;
    }

    const rememberQuery = this.query().trim() || item.title;
    pushRecentSearch(
      {
        query: rememberQuery,
        title: item.title,
        href: item.href !== '#' ? item.href : undefined,
      },
      { storageKey: this.recentStorageKey() },
    );
    this.recentTick.update((n) => n + 1);

    this.select.emit(item);
    this.closePalette();

    if (item.href && item.href !== '#') {
      if (item.href.startsWith('#')) {
        const target = document.querySelector(item.href);
        target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        return;
      }
      try {
        const url = new URL(item.href, window.location.href);
        if (url.origin === window.location.origin) {
          window.location.assign(`${url.pathname}${url.search}${url.hash}`);
        } else {
          window.open(url.href, '_blank', 'noopener,noreferrer');
        }
      } catch {
        window.location.assign(item.href);
      }
    }
  }

  private bindGlobalShortcut(): void {
    this.globalKeyHandler = (event: KeyboardEvent) => {
      const modK = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k';
      const slashOpen =
        event.key === '/' &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !this.open() &&
        !isEditableTarget(event.target);
      if (!modK && !slashOpen) {
        return;
      }
      event.preventDefault();
      if (modK && this.open()) {
        this.closePalette();
        return;
      }
      this.openPalette();
    };
    document.addEventListener('keydown', this.globalKeyHandler);
  }

  private unbindGlobalShortcut(): void {
    if (this.globalKeyHandler) {
      document.removeEventListener('keydown', this.globalKeyHandler);
      this.globalKeyHandler = null;
    }
  }
}
