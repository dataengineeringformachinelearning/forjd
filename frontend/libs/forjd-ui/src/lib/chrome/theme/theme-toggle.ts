import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { suiteThemeToggleAriaLabel } from '../../core/a11y/theme';
import { FjThemeService } from './theme.service';

/** forjd-theme-toggle — suite theme control with system + persistence. */
@Component({
  selector: 'forjd-theme-toggle',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'suite-theme-toggle-host fj-theme-toggle-host' },
  template: `
    <button
      type="button"
      class="suite-theme-toggle fj-theme-toggle theme-toggle-btn"
      [attr.aria-label]="ariaLabel()"
      [attr.title]="ariaLabel()"
      [attr.data-theme]="theme.theme()"
      [attr.data-preference]="theme.preference()"
      (click)="theme.toggleTheme()"
    >
      @if (theme.theme() === 'dark') {
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="4" />
          <path
            d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"
          />
        </svg>
      } @else {
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
        </svg>
      }
    </button>
  `,
})
export class FjThemeToggle {
  protected readonly theme = inject(FjThemeService);

  protected readonly ariaLabel = computed(() =>
    suiteThemeToggleAriaLabel(this.theme.preference(), this.theme.theme()),
  );
}
