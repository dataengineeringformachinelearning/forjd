import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjStatusList } from './status-list';

const meta: Meta<FjStatusList> = {
  title: 'Primitives/StatusList',
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
