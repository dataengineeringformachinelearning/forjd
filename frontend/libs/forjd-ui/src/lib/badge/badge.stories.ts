import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjBadge } from './badge';

const meta: Meta<FjBadge> = {
  title: 'Primitives/Badge',
  component: FjBadge,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: 'select',
      options: [
        'neutral',
        'accent',
        'secondary',
        'success',
        'warning',
        'danger',
        'info',
        'muted',
      ],
    },
  },
  render: (args) => ({
    props: args,
    template: `<forjd-badge [tone]="tone">Status</forjd-badge>`,
  }),
};

export default meta;
type Story = StoryObj<FjBadge>;

export const Neutral: Story = { args: { tone: 'neutral' } };
export const Accent: Story = { args: { tone: 'accent' } };
export const Danger: Story = { args: { tone: 'danger' } };
