import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjStatusList } from './status-list';

const meta: Meta<FjStatusList> = {
  title: 'Product/StatusList',
  component: FjStatusList,
  tags: ['autodocs'],
  args: {
    items: [
      { name: 'api', ok: true },
      { name: 'engine', ok: true },
      { name: 'postgres', ok: false, stateLabel: 'down' },
    ],
  },
  render: (args) => ({
    props: args,
    template: `<forjd-status-list [items]="items" style="width: 20rem; display: block;" />`,
  }),
};

export default meta;
type Story = StoryObj<FjStatusList>;

export const Mixed: Story = {};

export const AllOk: Story = {
  args: {
    items: [
      { name: 'api', ok: true },
      { name: 'engine', ok: true },
    ],
  },
};

export const AllDown: Story = {
  args: {
    items: [
      { name: 'api', ok: false, stateLabel: 'unreachable' },
      { name: 'engine', ok: false, stateLabel: 'down' },
      { name: 'postgres', ok: false, stateLabel: 'down' },
    ],
  },
};

export const Empty: Story = {
  args: {
    items: [],
  },
};
