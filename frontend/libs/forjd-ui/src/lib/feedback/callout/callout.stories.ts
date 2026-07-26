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
export const Success: Story = {
  args: { tone: 'success', heading: 'Sealed ingest accepted' },
};
export const Warning: Story = {
  args: { tone: 'warning', heading: 'Check tenant binding' },
};
export const Danger: Story = {
  args: { tone: 'danger', heading: 'Token rejected' },
};
export const Info: Story = {
  args: { tone: 'info', heading: 'Operational note' },
};

export const AllTones: Story = {
  name: 'Gallery / all tones',
  render: () => ({
    imports: [FjCallout],
    template: `
      <div style="display:grid;gap:var(--suite-space-2);width:min(28rem,92vw)">
        <forjd-callout tone="accent" heading="Accent">Command / confirmation.</forjd-callout>
        <forjd-callout tone="success" heading="Success">Quiet confirmation.</forjd-callout>
        <forjd-callout tone="warning" heading="Warning">Degraded dependency.</forjd-callout>
        <forjd-callout tone="danger" heading="Danger">Fail-closed auth.</forjd-callout>
        <forjd-callout tone="info" heading="Info">Operational note.</forjd-callout>
        <forjd-callout tone="muted" heading="Muted">Low-emphasis notice.</forjd-callout>
      </div>
    `,
  }),
};
