import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjButton } from './button';

/**
 * Primary action control — first forjd-ui primitive.
 * Add variants here as the library grows; Chromatic snapshots each story.
 */
const meta: Meta<FjButton> = {
  title: 'Primitives/Button',
  component: FjButton,
  tags: ['autodocs'],
  args: {
    variant: 'primary',
    type: 'button',
  },
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'ghost'],
    },
    type: {
      control: 'select',
      options: ['button', 'submit', 'reset'],
    },
  },
  render: (args) => ({
    props: args,
    template: `<forjd-button [variant]="variant" [type]="type">Button</forjd-button>`,
  }),
};

export default meta;
type Story = StoryObj<FjButton>;

export const Primary: Story = {
  args: { variant: 'primary' },
};

export const Ghost: Story = {
  args: { variant: 'ghost' },
};
