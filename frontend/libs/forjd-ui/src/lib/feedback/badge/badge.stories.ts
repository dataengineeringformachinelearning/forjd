import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjBadge } from './badge';

const meta: Meta<FjBadge> = {
  title: 'Primitives/Badge',
  component: FjBadge,
  tags: ['autodocs'],
  argTypes: {
    tone: {
      control: 'select',
      options: ['neutral', 'accent', 'secondary', 'success', 'warning', 'danger', 'info', 'muted'],
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
export const Success: Story = { args: { tone: 'success' } };
export const Warning: Story = { args: { tone: 'warning' } };
export const Danger: Story = { args: { tone: 'danger' } };
export const Info: Story = { args: { tone: 'info' } };
export const Muted: Story = { args: { tone: 'muted' } };

export const AllTones: Story = {
  name: 'Gallery / all tones',
  render: () => ({
    imports: [FjBadge],
    template: `
      <div style="display:flex;flex-wrap:wrap;gap:var(--suite-space-2)">
        <forjd-badge tone="neutral">Neutral</forjd-badge>
        <forjd-badge tone="accent">Accent</forjd-badge>
        <forjd-badge tone="success">Success</forjd-badge>
        <forjd-badge tone="warning">Warning</forjd-badge>
        <forjd-badge tone="danger">Danger</forjd-badge>
        <forjd-badge tone="info">Info</forjd-badge>
        <forjd-badge tone="muted">Muted</forjd-badge>
      </div>
    `,
  }),
};
