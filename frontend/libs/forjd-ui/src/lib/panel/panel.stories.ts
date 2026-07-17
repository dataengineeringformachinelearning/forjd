import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjPanel } from './panel';

const meta: Meta<FjPanel> = {
  title: 'Primitives/Panel',
  component: FjPanel,
  tags: ['autodocs'],
  args: {
    title: 'Stack',
  },
  render: (args) => ({
    props: args,
    template: `
      <forjd-panel [title]="title" style="width: 20rem; text-align: left;">
        <p class="fj-muted">Panel body content.</p>
      </forjd-panel>
    `,
  }),
};

export default meta;
type Story = StoryObj<FjPanel>;

export const Default: Story = {};

export const Untitled: Story = {
  args: { title: undefined },
};
