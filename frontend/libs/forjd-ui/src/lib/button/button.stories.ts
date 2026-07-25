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
    href: undefined,
    target: '_self',
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

export const Primary: Story = {
  args: { variant: 'primary' },
};

export const Ghost: Story = {
  args: { variant: 'ghost' },
};

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

export const GhostAsLink: Story = {
  args: {
    variant: 'ghost',
    href: 'https://backend.forjd.co/redoc',
    target: '_blank',
  },
  render: (args) => ({
    props: args,
    template: `
      <forjd-button [variant]="variant" [href]="href" [target]="target">
        ReDoc
      </forjd-button>
    `,
  }),
};
