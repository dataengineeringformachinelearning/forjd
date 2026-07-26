import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjField } from './field';
import { FjInput } from '../input/input';

const meta: Meta<FjField> = {
  title: 'Primitives/Field',
  component: FjField,
  tags: ['autodocs'],
  render: (args) => ({
    props: args,
    moduleMetadata: { imports: [FjInput] },
    template: `
      <forjd-field
        [label]="label"
        [description]="description"
        [error]="error"
        [required]="required"
        style="width: min(100%, 22rem)"
      >
        <forjd-input placeholder="tenant-id" />
      </forjd-field>
    `,
  }),
  args: {
    label: 'Tenant',
    description: 'Mapped FORJD tenant UUID',
    error: '',
    required: true,
  },
};

export default meta;
type Story = StoryObj<FjField>;

export const Default: Story = {};
export const Invalid: Story = {
  args: {
    error: 'Tenant ID is required',
  },
};
