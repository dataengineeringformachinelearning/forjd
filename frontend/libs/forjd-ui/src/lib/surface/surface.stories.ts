import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjAvatar } from '../avatar/avatar';
import { FjBadge } from '../badge/badge';
import { FjButton } from '../button/button';
import { FjCard } from '../card/card';
import { FjEmpty } from '../empty/empty';
import { FjNav } from '../nav/nav';
import { FjSeparator } from '../separator/separator';
import { FjSkeleton } from '../skeleton/skeleton';
import { FjTable } from '../table/table';
import { FjTabs } from '../tabs/tabs';

const meta: Meta = {
  title: 'Primitives/Surface',
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj;

export const CardNavTabsTable: Story = {
  render: () => ({
    imports: [
      FjCard,
      FjBadge,
      FjAvatar,
      FjSeparator,
      FjNav,
      FjTabs,
      FjTable,
      FjSkeleton,
      FjEmpty,
      FjButton,
    ],
    props: {
      nav: [
        { label: 'Docs', href: '#', active: true },
        { label: 'API', href: '#' },
      ],
      tabs: [
        { id: 'overview', label: 'Overview' },
        { id: 'events', label: 'Events' },
      ],
      columns: [
        { key: 'tenant', label: 'Tenant' },
        { key: 'status', label: 'Status' },
      ],
      rows: [
        { tenant: 'acme', status: 'healthy' },
        { tenant: 'northwind', status: 'degraded' },
      ],
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
            Dense table + empty + skeleton on suite chrome.
          </forjd-tabs>
          <forjd-table [columns]="columns" [rows]="rows" />
        </forjd-card>
        <forjd-skeleton variant="rect" />
        <forjd-empty title="No projections" description="Ingest events to populate stream_results.">
          <forjd-button variant="outline">Open docs</forjd-button>
        </forjd-empty>
      </div>
    `,
  }),
};
