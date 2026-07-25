import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjButton } from './button';

/**
 * Suite button — thin adapter over viking-button.
 * Chromatic baselines should match ui.deml.app Button stories.
 */
const meta: Meta<FjButton> = {
  title: 'Primitives/Button',
  component: FjButton,
  tags: ['autodocs'],
  args: {
    variant: 'primary',
    type: 'button',
    href: undefined,
    target: '_self',
  },
  argTypes: {
    variant: {
      control: 'select',
      options: ['primary', 'secondary', 'outline', 'danger', 'ghost'],
    },
    type: {
      control: 'select',
      options: ['button', 'submit', 'reset'],
    },
    href: { control: 'text' },
    target: {
      control: 'select',
      options: ['_self', '_blank'],
    },
  },
  render: (args) => ({
    props: args,
    template: `
      <forjd-button
        [variant]="variant"
        [type]="type"
        [href]="href"
        [target]="target"
      >Button</forjd-button>
    `,
  }),
};

export default meta;
type Story = StoryObj<FjButton>;

export const Primary: Story = { args: { variant: 'primary' } };
export const Secondary: Story = { args: { variant: 'secondary' } };
export const Outline: Story = { args: { variant: 'outline' } };
export const Danger: Story = { args: { variant: 'danger' } };
export const Ghost: Story = { args: { variant: 'ghost' } };

export const AsLink: Story = {
  args: {
    variant: 'primary',
    href: 'https://backend.forjd.co/docs',
    target: '_blank',
  },
  render: (args) => ({
    props: args,
    template: `
      <forjd-button [variant]="variant" [href]="href" [target]="target">
        Swagger
      </forjd-button>
    `,
  }),
};
