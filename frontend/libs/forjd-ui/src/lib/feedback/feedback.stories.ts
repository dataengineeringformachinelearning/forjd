import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjButton } from '../forms/button/button';
import { FjEmpty } from './empty/empty';
import { FjErrorState } from './error-state/error-state';
import { FjLoading, FjLoadingOverlay } from './loading/loading';
import { FjPageSkeleton } from './page-skeleton/page-skeleton';
import { FjSkeleton } from './skeleton/skeleton';
import { FjStreamStatus } from './stream-status/stream-status';

/**
 * Feedback surfaces — empty / loading / error / skeleton states.
 * (Legacy `empty.stories.ts` title remapped here for Primitives taxonomy.)
 */
const meta: Meta = {
  title: 'Primitives/Feedback',
  tags: ['autodocs'],
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

export const EmptyDefault: Story = {
  name: 'Empty / default',
  render: () => ({
    imports: [FjEmpty, FjButton],
    template: `
      <forjd-empty
        title="No sealed events yet"
        description="Ingest starts when a partner posts a sealed envelope with a tenant-bound service token."
        hint="POST /api/v1/ingest/events:batch"
        eyebrow="Getting started"
      >
        <forjd-button variant="primary">View ingest docs</forjd-button>
        <forjd-button variant="outline">Copy sample curl</forjd-button>
      </forjd-empty>
    `,
  }),
};

export const EmptyCompact: Story = {
  name: 'Empty / compact inset',
  render: () => ({
    imports: [FjEmpty],
    template: `
      <forjd-empty
        density="compact"
        variant="inset"
        title="No rows"
        description="Nothing matches this filter."
        [showIcon]="false"
      />
    `,
  }),
};

export const LoadingInline: Story = {
  name: 'Loading / inline',
  render: () => ({
    imports: [FjLoading],
    template: `
      <forjd-loading
        message="Hydrating projections"
        detail="Reading stream_results checkpoints for this tenant…"
      />
    `,
  }),
};

export const LoadingOverlayContained: Story = {
  name: 'Loading / overlay (contained)',
  render: () => ({
    imports: [FjLoadingOverlay],
    template: `
      <div style="position:relative;min-height:12rem;border:1px solid var(--suite-border);border-radius:var(--suite-radius-surface)">
        <forjd-loading-overlay
          message="Refreshing"
          detail="Polling /ready…"
        />
      </div>
    `,
  }),
};

export const SkeletonVariants: Story = {
  name: 'Skeleton / variants',
  render: () => ({
    imports: [FjSkeleton],
    template: `
      <div style="display:grid;gap:var(--suite-space-3);width:min(24rem,92vw)">
        <forjd-skeleton variant="text" />
        <forjd-skeleton variant="text" width="60%" />
        <forjd-skeleton variant="rect" height="4rem" />
        <forjd-skeleton variant="circle" width="2.5rem" height="2.5rem" />
        <div class="suite-skeleton-stack" role="status" aria-label="Loading card">
          <forjd-skeleton variant="rect" height="3rem" />
          <forjd-skeleton variant="text" />
          <forjd-skeleton variant="text" width="40%" />
        </div>
      </div>
    `,
  }),
};

export const PageSkeletonDashboard: Story = {
  name: 'Page skeleton / dashboard',
  render: () => ({
    imports: [FjPageSkeleton],
    template: `<forjd-page-skeleton layout="dashboard" label="Loading dashboard" />`,
  }),
};

export const PageSkeletonCards: Story = {
  name: 'Page skeleton / cards',
  render: () => ({
    imports: [FjPageSkeleton],
    template: `<forjd-page-skeleton layout="cards" />`,
  }),
};

export const PageSkeletonList: Story = {
  name: 'Page skeleton / list',
  render: () => ({
    imports: [FjPageSkeleton],
    template: `<forjd-page-skeleton layout="list" />`,
  }),
};

export const PageSkeletonForm: Story = {
  name: 'Page skeleton / form',
  render: () => ({
    imports: [FjPageSkeleton],
    template: `<forjd-page-skeleton layout="form" />`,
  }),
};

export const ErrorWithActions: Story = {
  name: 'Error state / recovery',
  render: () => ({
    imports: [FjErrorState, FjButton],
    template: `
      <forjd-error-state
        title="Projection feed unavailable"
        description="Dragonfly timed out while reading the tenant stream. Your data is safe — retry in a moment."
        hint="request_id · 7f3a…c912"
      >
        <forjd-button variant="primary">Retry</forjd-button>
        <forjd-button variant="ghost">Open status</forjd-button>
      </forjd-error-state>
    `,
  }),
};

export const StreamStatusUpdating: Story = {
  name: 'Stream status / updating',
  render: () => ({
    imports: [FjStreamStatus],
    template: `
      <forjd-stream-status
        phase="updating"
        label="Updating"
        tone="accent"
        [pulse]="true"
        ariaLabel="Receiving near real-time updates"
      />
    `,
  }),
};

export const StreamStatusDelayed: Story = {
  name: 'Stream status / delayed',
  render: () => ({
    imports: [FjStreamStatus],
    template: `
      <forjd-stream-status
        phase="delayed"
        label="Updates delayed"
        tone="warning"
        [pulse]="false"
        ariaLabel="Updates delayed"
      />
    `,
  }),
};

export const StreamStatusPaused: Story = {
  name: 'Stream status / paused',
  render: () => ({
    imports: [FjStreamStatus],
    template: `
      <forjd-stream-status
        phase="paused"
        label="Paused"
        tone="muted"
        [pulse]="false"
        ariaLabel="Updates paused"
      />
    `,
  }),
};
