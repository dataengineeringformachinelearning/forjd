import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  PLATFORM_ID,
  afterNextRender,
  computed,
  inject,
} from '@angular/core';
import { FjButton, FjPageShell, FjPanel, FjSection, FjSeparator } from 'forjd-ui';

import { environment } from '../../environments/environment';
import { createFetchHandle } from '../core/fetch/fetch-handle';
import { settleReadyStatus } from '../core/fetch/ready-fetch';
import { subscribeOnlineStatus } from '../core/offline/network';
import {
  probeLandingReady,
  retryLandingReady,
  shouldRefreshLandingReadyOnVisible,
  staleLandingReady,
  subscribeLandingReady,
} from '../core/ready/landing-ready';
import {
  LANDING_STEPS,
  LANDING_TITLE,
  landingReadyStory,
  landingSuiteLinks,
  type LandingReadyError,
} from './landing.content';

// --- Public product landing (fetch + SWR; ADR-0010 / ADR-0011 / ADR-0012) ---
@Component({
  selector: 'app-landing',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FjButton, FjPageShell, FjPanel, FjSection, FjSeparator],
  templateUrl: './landing.html',
})
export class Landing {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly title = LANDING_TITLE;
  protected readonly links = landingSuiteLinks(environment.apiBaseUrl);
  protected readonly steps = LANDING_STEPS;

  /**
   * `/ready` via shared fetch handle — loading | success | error.
   * Soft failures live in `error` (`not_ready` | `unreachable` | `offline`).
   * SWR updates apply via `applySettled` (no loading flash).
   */
  private readonly ready = createFetchHandle<'ok', LandingReadyError>({
    initialPhase: 'loading',
  });

  /** Single story object for badge / edge / retry (loading → ready → degraded). */
  protected readonly readyStory = computed(() =>
    landingReadyStory({
      loading: this.ready.isLoading() || this.ready.isIdle(),
      error: this.ready.isError() ? this.ready.error() : null,
    }),
  );

  protected readonly readyIsLive = computed(() => this.readyStory().phase === 'ready');
  protected readonly readyShowDegraded = computed(() => this.readyStory().phase === 'degraded');

  constructor() {
    afterNextRender(() => {
      if (!isPlatformBrowser(this.platformId)) {
        return;
      }

      const unsubCache = subscribeLandingReady((status) => {
        this.ready.applySettled(settleReadyStatus(status));
      });

      void this.loadReady();

      const unsubOnline = subscribeOnlineStatus((online) => {
        if (!online) {
          this.ready.fail('offline');
          return;
        }
        retryLandingReady();
        void this.loadReady();
      });

      const onVisibility = () => {
        if (document.visibilityState !== 'visible') {
          return;
        }
        // Constrained radios: skip while SWR cache is still fresh.
        if (!shouldRefreshLandingReadyOnVisible()) {
          return;
        }
        staleLandingReady();
        void this.loadReady({ silent: true });
      };
      document.addEventListener('visibilitychange', onVisibility);

      this.destroyRef.onDestroy(() => {
        unsubCache();
        unsubOnline();
        document.removeEventListener('visibilitychange', onVisibility);
        this.ready.abort();
      });
    });
  }

  /** Re-probe after soft failure — primary narrative stays painted. */
  protected retryProbe(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    retryLandingReady();
    void this.loadReady();
  }

  private async loadReady(options?: { silent?: boolean }): Promise<void> {
    if (options?.silent) {
      const status = await probeLandingReady(this.links.apiBaseUrl);
      this.ready.applySettled(settleReadyStatus(status));
      return;
    }
    await this.ready.runSettled(async () => {
      const status = await probeLandingReady(this.links.apiBaseUrl);
      return settleReadyStatus(status);
    });
  }
}
