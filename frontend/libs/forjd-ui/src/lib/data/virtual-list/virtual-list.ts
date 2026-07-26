import { NgTemplateOutlet } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  OnDestroy,
  TemplateRef,
  computed,
  contentChild,
  input,
  signal,
  viewChild,
} from '@angular/core';

import { FjErrorState } from '../../feedback/error-state/error-state';
import { computeVirtualWindow, indicesForWindow } from './virtual-window';

export type FjVirtualListItemContext<T> = {
  $implicit: T;
  index: number;
};

/** Default item shape when callers do not specialize T. */
export type FjVirtualListItem = {
  readonly id?: string | number;
};

/** forjd-virtual-list — fixed-height windowed list (suite adapter, zero CDK). */
@Component({
  selector: 'forjd-virtual-list',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [NgTemplateOutlet, FjErrorState],
  host: {
    class: 'suite-virtual-list fj-virtual-list viking-virtual-list',
  },
  template: `
    @if (error()) {
      <forjd-error-state [title]="errorTitle()" [description]="error()" [hint]="errorHint()" />
    } @else {
      <div
        #viewport
        class="suite-virtual-list__viewport fj-virtual-list__viewport viking-virtual-list__viewport"
        [style.height]="height()"
        [attr.aria-label]="label()"
        role="list"
        tabindex="0"
        (scroll)="onScroll()"
      >
        <div class="suite-virtual-list__spacer" [style.height.px]="totalHeight()">
          <div
            class="suite-virtual-list__window"
            [style.transform]="'translate3d(0, ' + offsetY() + 'px, 0)'"
          >
            @for (index of visibleIndices(); track trackIndex(index)) {
              <div
                class="suite-virtual-list__item fj-virtual-list__item"
                [style.height.px]="itemHeight()"
                role="listitem"
                [attr.aria-setsize]="items().length"
                [attr.aria-posinset]="index + 1"
              >
                @if (itemTemplate(); as tpl) {
                  <ng-container
                    [ngTemplateOutlet]="tpl"
                    [ngTemplateOutletContext]="{ $implicit: items()[index], index }"
                  />
                }
              </div>
            }
          </div>
        </div>
      </div>
    }
  `,
})
export class FjVirtualList<T = FjVirtualListItem> implements AfterViewInit, OnDestroy {
  readonly items = input<readonly T[]>([]);
  readonly itemHeight = input(96);
  readonly height = input('24rem');
  readonly overscan = input(4);
  readonly label = input('Scrollable list');
  /** When set, show FjErrorState instead of the windowed list. */
  readonly error = input('');
  readonly errorTitle = input('Could not load list');
  readonly errorHint = input('');
  readonly trackBy = input<((item: T, index: number) => string | number) | null>(null);

  protected readonly itemTemplate =
    contentChild<TemplateRef<FjVirtualListItemContext<T>>>(TemplateRef);

  private readonly viewport = viewChild<ElementRef<HTMLElement>>('viewport');
  private readonly scrollTop = signal(0);
  private readonly viewportHeightPx = signal(0);
  private resizeObserver: ResizeObserver | null = null;
  private scrollRaf = 0;
  private measureRaf = 0;

  /** Private math snapshot — peel into flat computeds for the template. */
  private readonly windowMetrics = computed(() =>
    computeVirtualWindow({
      scrollTop: this.scrollTop(),
      viewportHeight: this.viewportHeightPx(),
      itemCount: this.items().length,
      itemHeight: this.itemHeight(),
      overscan: this.overscan(),
    }),
  );

  protected readonly totalHeight = computed(() => this.windowMetrics().totalHeight);
  protected readonly offsetY = computed(() => this.windowMetrics().offsetY);
  protected readonly visibleIndices = computed(() => {
    const { start, end } = this.windowMetrics();
    return indicesForWindow(start, end);
  });

  ngAfterViewInit(): void {
    const el = this.viewport()?.nativeElement;
    if (!el) {
      return;
    }
    this.scheduleMeasure(el);
    if (typeof ResizeObserver !== 'undefined') {
      this.resizeObserver = new ResizeObserver((entries) => {
        const height = entries[0]?.contentRect.height;
        if (height != null && height !== this.viewportHeightPx()) {
          this.viewportHeightPx.set(Math.round(height));
        }
      });
      this.resizeObserver.observe(el);
    }
  }

  ngOnDestroy(): void {
    this.resizeObserver?.disconnect();
    this.resizeObserver = null;
    if (this.scrollRaf) {
      cancelAnimationFrame(this.scrollRaf);
      this.scrollRaf = 0;
    }
    if (this.measureRaf) {
      cancelAnimationFrame(this.measureRaf);
      this.measureRaf = 0;
    }
  }

  protected onScroll(): void {
    if (this.scrollRaf) {
      return;
    }
    this.scrollRaf = requestAnimationFrame(() => {
      this.scrollRaf = 0;
      const next = this.viewport()?.nativeElement.scrollTop;
      if (next == null) {
        return;
      }
      if (next !== this.scrollTop()) {
        this.scrollTop.set(next);
      }
    });
  }

  protected trackIndex(index: number): string | number {
    const track = this.trackBy();
    const item = this.items()[index];
    return track && item !== undefined ? track(item, index) : index;
  }

  private scheduleMeasure(el: HTMLElement): void {
    if (this.measureRaf) {
      return;
    }
    this.measureRaf = requestAnimationFrame(() => {
      this.measureRaf = 0;
      const height = el.clientHeight;
      const top = el.scrollTop;
      if (height !== this.viewportHeightPx()) {
        this.viewportHeightPx.set(height);
      }
      if (top !== this.scrollTop()) {
        this.scrollTop.set(top);
      }
    });
  }
}
