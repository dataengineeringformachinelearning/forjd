import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjPanel } from './panel';

const meta: Meta<FjPanel> = {
  title: 'Product/Panel',
  component: FjPanel,
  tags: ['autodocs'],
  args: {
    title: 'Stack',
    variant: 'section',
  },
  argTypes: {
    title: { control: 'text' },
    variant: {
      control: 'select',
      options: ['section', 'card'],
    },
  },
  render: (args) => ({
    props: args,
    template: `
      <forjd-panel [title]="title" [variant]="variant" class="sb-panel">
        <p class="fj-muted">Panel body content.</p>
      </forjd-panel>
    `,
    styles: [
      `
        .sb-panel {
          display: block;
          width: 20rem;
          text-align: left;
        }
      `,
    ],
  }),
};

export default meta;
type Story = StoryObj<FjPanel>;

export const Default: Story = {};

export const Card: Story = {
  args: {
    title: 'Sealed ingest',
    variant: 'card',
  },
};

export const Untitled: Story = {
  args: { title: undefined, variant: 'section' },
};
