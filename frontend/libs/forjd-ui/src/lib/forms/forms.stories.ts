import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjCheckbox } from './checkbox/checkbox';
import { FjField } from './field/field';
import { FjInput } from './input/input';
import { FjSelect } from './select/select';
import { FjSwitch } from './switch/switch';
import { FjTextarea } from './textarea/textarea';

const meta: Meta = {
  title: 'Primitives/Forms',
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj;

const options = [
  { label: 'Streaming', value: 'stream' },
  { label: 'Batch', value: 'batch' },
];

export const Stack: Story = {
  name: 'Stack / default',
  render: () => ({
    imports: [FjField, FjInput, FjTextarea, FjSelect, FjCheckbox, FjSwitch],
    props: { options },
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

export const FieldError: Story = {
  name: 'Field / error',
  render: () => ({
    imports: [FjField, FjInput],
    template: `
      <div style="width:min(22rem,90vw)">
        <forjd-field
          label="Tenant id"
          description="UUID from partner bind"
          error="Must be a valid UUID"
          [required]="true"
        >
          <forjd-input value="not-a-uuid" autocomplete="off" />
        </forjd-field>
      </div>
    `,
  }),
};

export const Disabled: Story = {
  name: 'Controls / disabled',
  render: () => ({
    imports: [FjField, FjInput, FjTextarea, FjSelect, FjCheckbox, FjSwitch],
    props: { options },
    template: `
      <div style="display:grid;gap:var(--suite-space-3);width:min(22rem,90vw)">
        <forjd-field label="Email">
          <forjd-input type="email" value="locked@forjd.co" [disabled]="true" />
        </forjd-field>
        <forjd-field label="Mode">
          <forjd-select [options]="options" value="stream" [disabled]="true" />
        </forjd-field>
        <forjd-field label="Notes">
          <forjd-textarea [disabled]="true" value="Read-only notes" />
        </forjd-field>
        <forjd-checkbox [checked]="true" [disabled]="true">Sealed lane</forjd-checkbox>
        <forjd-switch [checked]="true" [disabled]="true">Live updates</forjd-switch>
      </div>
    `,
  }),
};

export const Checked: Story = {
  name: 'Controls / checked',
  render: () => ({
    imports: [FjCheckbox, FjSwitch],
    template: `
      <div style="display:grid;gap:var(--suite-space-3);width:min(22rem,90vw)">
        <forjd-checkbox [checked]="true" description="Required for partners">
          Accept ciphertext-only lane
        </forjd-checkbox>
        <forjd-checkbox [checked]="false">Optional detector pack</forjd-checkbox>
        <forjd-switch [checked]="true">Theme follows system</forjd-switch>
        <forjd-switch [checked]="false">Include search history in export</forjd-switch>
      </div>
    `,
  }),
};
