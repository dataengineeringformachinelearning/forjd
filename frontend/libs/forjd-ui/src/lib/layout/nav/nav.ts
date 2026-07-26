import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { nextRovingIndexHorizontal } from '../../core/a11y/focus';
import { safeHref } from '../../core/a11y/safe-href';

export interface FjNavItem {
  label: string;
  href: string;
  active?: boolean;
  external?: boolean;
}

@Component({
  selector: 'forjd-nav',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'suite-nav fj-nav viking-nav' },
  template: `
    <nav
      class="suite-nav-inner fj-nav-inner viking-nav-inner"
      [attr.aria-label]="ariaLabel()"
      (keydown)="onKeydown($event)"
    >
      @for (item of safeItems(); track item.href; let i = $index) {
        <a
          class="suite-nav-link fj-nav-link viking-nav-link"
          [attr.href]="item.href"
          [attr.data-active]="item.active ? 'true' : null"
          [attr.aria-current]="item.active ? 'page' : null"
          [attr.target]="item.external ? '_blank' : null"
          [attr.rel]="item.external ? 'noopener noreferrer' : null"
          [attr.data-nav-index]="i"
        >
          {{ item.label }}
        </a>
      }
      <ng-content />
    </nav>
  `,
})
export class FjNav {
  readonly items = input<readonly FjNavItem[]>([]);
  readonly ariaLabel = input('Primary');

  /** Strip unsafe hrefs before paint (ADR-0013). */
  protected readonly safeItems = computed(() =>
    this.items()
      .map((item) => {
        const href = safeHref(item.href);
        return href ? { ...item, href } : null;
      })
      .filter((item): item is FjNavItem => item != null),
  );

  protected onKeydown(event: KeyboardEvent): void {
    const root = event.currentTarget as HTMLElement | null;
    if (!root) return;
    const links = Array.from(
      root.querySelectorAll<HTMLAnchorElement>('.suite-nav-link, .fj-nav-link, .viking-nav-link'),
    );
    if (links.length === 0) return;

    const currentIndex = Math.max(
      0,
      links.findIndex((link) => link === document.activeElement),
    );
    const nextIndex = nextRovingIndexHorizontal(event.key, currentIndex, links.length);
    if (nextIndex === null) return;

    event.preventDefault();
    links[nextIndex]?.focus();
  }
}
