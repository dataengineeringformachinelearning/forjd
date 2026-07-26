import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjTable } from '../data/table/table';
import { FjTabPanel } from '../data/tabs/tab-panel';
import { FjTabs } from '../data/tabs/tabs';
import { FjBadge } from '../feedback/badge/badge';
import { FjDisclosure } from '../feedback/disclosure/disclosure';
import { FjEmpty } from '../feedback/empty/empty';
import { FjSkeleton } from '../feedback/skeleton/skeleton';
import { FjButton } from '../forms/button/button';
import { FjAvatar } from './avatar/avatar';
import { FjCard } from './card/card';
import { FjNav } from './nav/nav';
import { FjSeparator } from './separator/separator';

const meta: Meta = {
  title: 'Primitives/Surface',
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj;

export const CardNavTabsTable: Story = {
  name: 'Composition / card nav tabs table',
  render: () => ({
    imports: [
      FjCard,
      FjBadge,
      FjAvatar,
      FjSeparator,
      FjNav,
      FjTabs,
      FjTabPanel,
      FjTable,
      FjSkeleton,
      FjEmpty,
      FjButton,
      FjDisclosure,
    ],
    props: {
      nav: [
        { label: 'Docs', href: '#', active: true },
        { label: 'API', href: '#' },
      ],
      tabs: [
        { id: 'overview', label: 'Overview' },
        { id: 'ops', label: 'Ops' },
      ],
      columns: [
        { key: 'tenant', label: 'Tenant' },
        { key: 'status', label: 'Status' },
      ],
      rows: [
        { id: 'acme', tenant: 'acme', status: 'healthy' },
        { id: 'northwind', tenant: 'northwind', status: 'degraded' },
      ],
      bulkActions: [{ id: 'export', label: 'Export', variant: 'secondary' }],
    },
    template: `
      <div style="display:grid;gap:var(--suite-space-3);width:min(36rem,92vw)">
        <forjd-nav [items]="nav" />
        <forjd-card>
          <div style="display:flex;align-items:center;gap:var(--suite-space-2)">
            <forjd-avatar name="Operator One" />
            <forjd-badge tone="success">Live</forjd-badge>
          </div>
          <forjd-separator />
          <forjd-tabs [tabs]="tabs" value="overview">
            <forjd-tab-panel value="overview">
              Dense table + empty + skeleton on suite chrome.
            </forjd-tab-panel>
            <forjd-tab-panel value="ops"> Operational metrics and leases. </forjd-tab-panel>
          </forjd-tabs>
          <forjd-table
            [columns]="columns"
            [rows]="rows"
            [selectable]="true"
            [bulkActions]="bulkActions"
          />
        </forjd-card>
        <forjd-disclosure
          sectionId="story.surface.advanced"
          heading="Advanced routing"
          description="Collapsed by default so essentials stay primary (ADR-0022)."
        >
          <p>Optional detector thresholds and replay windows live here.</p>
        </forjd-disclosure>
        <forjd-skeleton variant="rect" />
        <forjd-empty title="No projections" description="Ingest events to populate stream_results.">
          <forjd-button variant="outline">Open docs</forjd-button>
        </forjd-empty>
      </div>
    `,
  }),
};

export const DisclosureOpen: Story = {
  name: 'Disclosure / default open',
  render: () => ({
    imports: [FjDisclosure],
    template: `
      <forjd-disclosure
        style="display:block;width:min(36rem,92vw)"
        sectionId="story.surface.disclosure-open"
        heading="Replay window"
        description="Shown expanded for this story (defaultOpen)."
        [defaultOpen]="true"
        badge="Advanced"
      >
        <p>Optional detector thresholds and replay windows live here.</p>
      </forjd-disclosure>
    `,
  }),
};

export const CardInteractive: Story = {
  name: 'Card / interactive',
  render: () => ({
    imports: [FjCard],
    template: `
      <forjd-card [interactive]="true" style="display:block;width:min(20rem,92vw);padding:var(--suite-space-3)">
        Interactive card surface (data-interactive).
      </forjd-card>
    `,
  }),
};

export const AvatarSizes: Story = {
  name: 'Avatar / sizes',
  render: () => ({
    imports: [FjAvatar],
    template: `
      <div style="display:flex;align-items:center;gap:var(--suite-space-2)">
        <forjd-avatar name="Ada Lovelace" size="sm" />
        <forjd-avatar name="Ada Lovelace" size="md" />
        <forjd-avatar name="Ada Lovelace" size="lg" />
      </div>
    `,
  }),
};
