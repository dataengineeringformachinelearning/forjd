import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export interface FjNavItem {
  label: string;
  href: string;
  active?: boolean;
  external?: boolean;
}

@Component({
  selector: 'forjd-nav',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'suite-nav fj-nav' },
  template: `
    <nav class="suite-nav-inner fj-nav-inner" [attr.aria-label]="ariaLabel()">
      @for (item of items(); track item.href) {
        <a
          class="suite-nav-link fj-nav-link"
          [attr.href]="item.href"
          [attr.data-active]="item.active ? 'true' : null"
          [attr.target]="item.external ? '_blank' : null"
          [attr.rel]="item.external ? 'noopener noreferrer' : null"
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
}
