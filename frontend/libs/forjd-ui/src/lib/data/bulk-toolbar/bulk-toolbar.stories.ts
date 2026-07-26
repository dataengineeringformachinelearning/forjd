import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjBulkToolbar, type FjBulkAction } from './bulk-toolbar';

const actions: readonly FjBulkAction[] = [
  { id: 'export', label: 'Export', variant: 'secondary' },
  { id: 'archive', label: 'Archive', variant: 'outline' },
  { id: 'delete', label: 'Delete', variant: 'danger' },
];

const meta: Meta<FjBulkToolbar> = {
  title: 'Primitives/Bulk toolbar',
  component: FjBulkToolbar,
  tags: ['autodocs'],
  parameters: { layout: 'padded' },
  argTypes: {
    actionClick: { action: 'actionClick' },
    clear: { action: 'clear' },
  },
};

export default meta;
type Story = StoryObj<FjBulkToolbar>;

/** Default elevated bar — suite button interaction language. */
export const Default: Story = {
  args: {
    count: 3,
    actions,
    ariaLabel: 'Bulk actions',
  },
};

/** Danger-forward selection (destructive primary action). */
export const WithDanger: Story = {
  args: {
    count: 12,
    actions: [
      { id: 'revoke', label: 'Revoke access', variant: 'danger' },
      { id: 'export', label: 'Export', variant: 'secondary' },
    ],
  },
};

/** Disabled action while selection is valid. */
export const DisabledAction: Story = {
  args: {
    count: 2,
    actions: [
      { id: 'export', label: 'Export', variant: 'secondary' },
      { id: 'merge', label: 'Merge', variant: 'outline', disabled: true },
    ],
  },
};

/** Hidden when nothing is selected (host renders nothing). */
export const EmptySelection: Story = {
  args: {
    count: 0,
    actions,
  },
};
