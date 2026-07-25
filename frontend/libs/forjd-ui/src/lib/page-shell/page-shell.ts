import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

export type FjLayoutDensity = 'tight' | 'compact' | 'default' | 'loose';

/**
 * forjd-page-shell — suite spacing / max-width contract (token-only).
 * Chrome: suite-components.css (`.suite-page-shell` / `.fj-page-shell`).
 */
@Component({
  selector: 'forjd-page-shell',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class]': 'hostClass()' },
  template: `<ng-content />`,
})
export class FjPageShell {
  readonly spacing = input<FjLayoutDensity>('default');

  protected readonly hostClass = computed(() =>
    [
      'suite-page-shell',
      'fj-page-shell',
      this.spacing() === 'default' ? '' : `fj-stack--${this.spacing()}`,
    ]
      .filter(Boolean)
      .join(' '),
  );
}

@Component({
  selector: 'forjd-section',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'suite-section fj-section' },
  template: `<ng-content />`,
})
export class FjSection {}

@Component({
  selector: 'forjd-stack',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[class]': 'hostClass()' },
  template: `<ng-content />`,
})
export class FjStack {
  readonly spacing = input<FjLayoutDensity>('default');
  readonly centered = input(false);

  protected readonly hostClass = computed(() =>
    [
      'suite-stack',
      'fj-stack',
      this.spacing() === 'default' ? '' : `fj-stack--${this.spacing()}`,
      this.centered() ? 'fj-stack--center' : '',
    ]
      .filter(Boolean)
      .join(' '),
  );
}
