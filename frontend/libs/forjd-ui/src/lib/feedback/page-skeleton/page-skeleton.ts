import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { FjSkeleton } from '../skeleton/skeleton';

export type FjPageSkeletonLayout = 'dashboard' | 'cards' | 'list' | 'form' | 'nav';

/** forjd-page-skeleton — progressive loading shell (suite adapter). */
@Component({
  selector: 'forjd-page-skeleton',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjSkeleton],
  host: {
    class: 'suite-page-skeleton fj-page-skeleton viking-page-skeleton',
    role: 'status',
    'aria-busy': 'true',
    '[attr.aria-label]': 'label()',
    '[attr.data-layout]': 'layout()',
  },
  template: `
    @switch (layout()) {
      @case ('dashboard') {
        <div class="suite-page-skeleton__metrics">
          <div class="suite-skeleton-stack" aria-hidden="true">
            <forjd-skeleton variant="text" width="45%" height="1.25rem" />
            <forjd-skeleton variant="text" width="80%" />
            <forjd-skeleton variant="text" width="65%" />
          </div>
          <div class="suite-skeleton-stack" aria-hidden="true">
            <forjd-skeleton variant="text" width="40%" height="1.25rem" />
            <forjd-skeleton variant="text" width="75%" />
            <forjd-skeleton variant="text" width="55%" />
          </div>
        </div>
        <div class="suite-page-skeleton__charts">
          <div class="suite-skeleton-stack" aria-hidden="true">
            <forjd-skeleton variant="rect" height="12rem" />
            <forjd-skeleton variant="text" width="55%" />
          </div>
          <div class="suite-skeleton-stack" aria-hidden="true">
            <forjd-skeleton variant="rect" height="12rem" />
            <forjd-skeleton variant="text" width="62%" />
          </div>
        </div>
      }
      @case ('cards') {
        <div class="suite-page-skeleton__cards">
          @for (_ of cardSlots; track $index) {
            <div class="suite-skeleton-stack" aria-hidden="true">
              <forjd-skeleton variant="text" width="48%" height="1.25rem" />
              <forjd-skeleton variant="text" width="90%" />
              <forjd-skeleton variant="rect" height="3rem" />
            </div>
          }
        </div>
      }
      @case ('list') {
        <div class="suite-skeleton-stack suite-page-skeleton__list" aria-hidden="true">
          @for (_ of listSlots; track $index) {
            <forjd-skeleton variant="rect" height="4.5rem" />
          }
        </div>
      }
      @case ('form') {
        <div class="suite-skeleton-stack suite-page-skeleton__form" aria-hidden="true">
          <forjd-skeleton variant="text" width="40%" height="1.25rem" />
          <forjd-skeleton variant="rect" height="2.75rem" />
          <forjd-skeleton variant="rect" height="2.75rem" />
          <forjd-skeleton variant="rect" height="6rem" />
        </div>
      }
      @case ('nav') {
        <div class="suite-page-skeleton__nav" aria-hidden="true">
          @for (_ of navSlots; track $index) {
            <forjd-skeleton variant="text" width="72%" height="0.875rem" />
          }
        </div>
      }
    }
  `,
})
export class FjPageSkeleton {
  readonly layout = input<FjPageSkeletonLayout>('dashboard');
  readonly label = input('Loading');

  protected readonly cardSlots = [0, 1, 2];
  protected readonly listSlots = [0, 1, 2, 3, 4];
  protected readonly navSlots = [0, 1, 2, 3, 4, 5];
}
