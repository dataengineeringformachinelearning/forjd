import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjCheckbox } from '../checkbox/checkbox';
import { FjField } from '../field/field';
import { FjInput } from '../input/input';
import { FjSelect } from '../select/select';
import { FjSwitch } from '../switch/switch';
import { FjTextarea } from '../textarea/textarea';

const meta: Meta = {
  title: 'Primitives/Forms',
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj;

export const Stack: Story = {
  render: () => ({
    imports: [FjField, FjInput, FjTextarea, FjSelect, FjCheckbox, FjSwitch],
    props: {
      options: [
        { label: 'Streaming', value: 'stream' },
        { label: 'Batch', value: 'batch' },
      ],
    },
    template: `
      <div style="display:grid;gap:var(--suite-space-3);width:min(22rem,90vw)">
        <forjd-field label="Email" [required]="true">
          <forjd-input type="email" placeholder="ops@forjd.co" />
        </forjd-field>
        <forjd-field label="Mode" description="Suite select chrome">
          <forjd-select [options]="options" placeholder="Choose…" />
        </forjd-field>
        <forjd-field label="Notes">
          <forjd-textarea rows="3" placeholder="Owned styles only" />
        </forjd-field>
        <forjd-checkbox description="Tenant-bound service token">Enable sealed lane</forjd-checkbox>
        <forjd-switch>Live updates</forjd-switch>
      </div>
    `,
  }),
};
