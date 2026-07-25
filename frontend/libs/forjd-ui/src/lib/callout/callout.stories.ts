import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjCallout } from './callout';

const meta: Meta<FjCallout> = {
  title: 'Primitives/Callout',
  component: FjCallout,
  tags: ['autodocs'],
  args: {
    tone: 'accent',
    heading: 'Suite notice',
  },
  render: (args) => ({
    props: args,
    template: `
      <forjd-callout [tone]="tone" [heading]="heading" style="width: min(100%, 28rem)">
        Chrome matches deml.app / Viking-UI callouts.
      </forjd-callout>
    `,
  }),
};

export default meta;
type Story = StoryObj<FjCallout>;

export const Accent: Story = {};
export const Warning: Story = {
  args: { tone: 'warning', heading: 'Check tenant binding' },
};
