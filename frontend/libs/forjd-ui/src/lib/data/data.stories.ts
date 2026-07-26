import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjActivityList } from './activity-list/activity-list';
import { FjBulkToolbar } from './bulk-toolbar/bulk-toolbar';
import { FjPipelineFlow } from './pipeline-flow/pipeline-flow';
import { FjTable } from './table/table';
import { FjVirtualList } from './virtual-list/virtual-list';

const columns = [
  { key: 'tenant', label: 'Tenant' },
  { key: 'status', label: 'Status' },
];

const rows = [
  { id: 'acme', tenant: 'acme', status: 'healthy' },
  { id: 'northwind', tenant: 'northwind', status: 'degraded' },
  { id: 'contoso', tenant: 'contoso', status: 'healthy' },
];

const bulkActions = [
  { id: 'export', label: 'Export', variant: 'secondary' as const },
  { id: 'archive', label: 'Archive', variant: 'outline' as const },
];

const meta: Meta = {
  title: 'Primitives/Data',
  tags: ['autodocs'],
  parameters: { layout: 'padded' },
};

export default meta;
type Story = StoryObj;

export const TableDefault: Story = {
  name: 'Table / rows',
  render: () => ({
    imports: [FjTable],
    props: { columns, rows },
    template: `
      <forjd-table
        style="display:block;width:min(36rem,92vw)"
        [columns]="columns"
        [rows]="rows"
      />
    `,
  }),
};

export const TableSelectable: Story = {
  name: 'Table / selectable + bulk',
  render: () => ({
    imports: [FjTable],
    props: { columns, rows, bulkActions },
    template: `
      <forjd-table
        style="display:block;width:min(36rem,92vw)"
        [columns]="columns"
        [rows]="rows"
        [selectable]="true"
        [bulkActions]="bulkActions"
      />
    `,
  }),
};

export const TableLoading: Story = {
  name: 'Table / loading',
  render: () => ({
    imports: [FjTable],
    props: { columns },
    template: `
      <forjd-table
        style="display:block;width:min(36rem,92vw)"
        [columns]="columns"
        [rows]="[]"
        [loading]="true"
      />
    `,
  }),
};

export const TableError: Story = {
  name: 'Table / error',
  render: () => ({
    imports: [FjTable],
    props: { columns },
    template: `
      <forjd-table
        style="display:block;width:min(36rem,92vw)"
        [columns]="columns"
        [rows]="[]"
        error="Timed out reading stream_results for this tenant."
        errorTitle="Could not load rows"
        errorHint="request_id · demo-story"
      />
    `,
  }),
};

export const TableEmpty: Story = {
  name: 'Table / empty',
  render: () => ({
    imports: [FjTable],
    props: { columns },
    template: `
      <forjd-table
        style="display:block;width:min(36rem,92vw)"
        [columns]="columns"
        [rows]="[]"
        emptyTitle="No projections"
        emptyDescription="Ingest sealed events to populate this table."
      />
    `,
  }),
};

export const VirtualListWindowed: Story = {
  name: 'Virtual list / windowed',
  render: () => ({
    imports: [FjVirtualList],
    props: {
      items: Array.from({ length: 200 }, (_, i) => ({
        id: i,
        label: `Projection ${i + 1}`,
        detail: `checkpoint · shard ${(i % 8) + 1}`,
      })),
    },
    template: `
      <forjd-virtual-list
        style="display:block;width:min(28rem,92vw)"
        [items]="items"
        [itemHeight]="64"
        height="18rem"
        label="Projections"
      >
        <ng-template let-item let-index="index">
          <div style="padding:var(--suite-space-2);border-bottom:1px solid var(--suite-border)">
            <strong>{{ item.label }}</strong>
            <div style="color:var(--suite-ink-muted);font-size:var(--suite-text-sm)">
              {{ item.detail }} · #{{ index + 1 }}
            </div>
          </div>
        </ng-template>
      </forjd-virtual-list>
    `,
  }),
};

export const VirtualListError: Story = {
  name: 'Virtual list / error',
  render: () => ({
    imports: [FjVirtualList],
    template: `
      <forjd-virtual-list
        style="display:block;width:min(28rem,92vw)"
        [items]="[]"
        error="Could not page the projection feed."
        errorTitle="List unavailable"
        errorHint="Retry when Dragonfly is healthy."
      />
    `,
  }),
};

export const ActivityFilled: Story = {
  name: 'Activity / entries',
  render: () => ({
    imports: [FjActivityList],
    props: {
      entries: [
        {
          id: '1',
          at: Date.now() - 60_000,
          kind: 'preferences.theme',
          label: 'Theme set to dark',
          source: 'forjd' as const,
        },
        {
          id: '2',
          at: Date.now() - 120_000,
          kind: 'preferences.export',
          label: 'Exported local preferences',
          detail: 'Soft chrome pack',
          source: 'forjd' as const,
        },
        {
          id: '3',
          at: Date.now() - 300_000,
          kind: 'onboarding.complete',
          label: 'Finished partner deploy checklist',
          source: 'forjd' as const,
        },
      ],
    },
    template: `
      <forjd-activity-list
        style="display:block;width:min(28rem,92vw)"
        [entries]="entries"
      />
    `,
  }),
};

export const ActivityEmpty: Story = {
  name: 'Activity / empty',
  render: () => ({
    imports: [FjActivityList],
    props: { entries: [] },
    template: `
      <forjd-activity-list
        style="display:block;width:min(28rem,92vw)"
        [entries]="entries"
      />
    `,
  }),
};

export const BulkToolbarStandalone: Story = {
  name: 'Bulk toolbar / elevated',
  render: () => ({
    imports: [FjBulkToolbar],
    props: {
      count: 4,
      actions: [
        { id: 'export', label: 'Export', variant: 'secondary' as const },
        { id: 'delete', label: 'Delete', variant: 'danger' as const },
      ],
    },
    template: `
      <forjd-bulk-toolbar
        style="display:block;width:min(36rem,92vw)"
        [count]="count"
        [actions]="actions"
      />
    `,
  }),
};

export const PipelineFlowHorizontal: Story = {
  name: 'Pipeline / horizontal',
  render: () => ({
    imports: [FjPipelineFlow],
    props: {
      steps: [
        {
          id: 'rollup',
          title: 'Seal & roll up',
          detail: 'Aggregate ciphertext metadata into a durable projection.',
          kind: 'process' as const,
        },
        {
          id: 'size_anomaly',
          title: 'Size anomaly',
          detail: 'Flag unusually large envelopes.',
          kind: 'detect' as const,
        },
        {
          id: 'rate_anomaly',
          title: 'Rate anomaly',
          detail: 'Flag bursts over the rate window.',
          kind: 'detect' as const,
        },
      ],
    },
    template: `
      <forjd-pipeline-flow
        style="display:block;width:min(40rem,92vw)"
        [steps]="steps"
        orientation="horizontal"
        label="Threat telemetry steps"
      />
    `,
  }),
};

export const PipelineFlowEmpty: Story = {
  name: 'Pipeline / empty',
  render: () => ({
    imports: [FjPipelineFlow],
    props: { steps: [] },
    template: `
      <forjd-pipeline-flow
        style="display:block;width:min(28rem,92vw)"
        [steps]="steps"
      />
    `,
  }),
};
