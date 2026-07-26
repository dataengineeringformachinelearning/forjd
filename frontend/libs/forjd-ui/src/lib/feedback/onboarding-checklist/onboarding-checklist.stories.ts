import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjOnboardingChecklist } from './onboarding-checklist';

const partnerSteps = [
  {
    id: 'bind',
    title: 'Bind',
    description: 'Map a partner account to a FORJD tenant and mint fjsvc_.',
  },
  {
    id: 'seal',
    title: 'Seal',
    description: 'Clients seal events with X25519/HKDF + AES-256-GCM.',
  },
  {
    id: 'project',
    title: 'Project',
    description: 'Checkpoint durable stream_results with replay and DLQ.',
  },
  {
    id: 'operate',
    title: 'Operate',
    description: 'YAML workflows and rollups under tenant RLS.',
  },
];

const meta: Meta<FjOnboardingChecklist> = {
  title: 'Primitives/Onboarding',
  component: FjOnboardingChecklist,
  tags: ['autodocs'],
  parameters: { layout: 'padded' },
};
export default meta;

type Story = StoryObj<FjOnboardingChecklist>;

export const PartnerDeploy: Story = {
  name: 'Partner deploy / interactive',
  args: {
    flowId: 'forjd-partner',
    heading: 'Four steps to sealed streaming',
    description: 'Track Bind → Seal → Project → Operate as you integrate.',
    autoHide: false,
    steps: partnerSteps,
  },
};

export const NotDismissible: Story = {
  name: 'Partner deploy / not dismissible',
  args: {
    flowId: 'forjd-partner',
    heading: 'Required deploy sequence',
    description: 'Complete every step before dismissing.',
    dismissible: false,
    autoHide: false,
    steps: partnerSteps,
  },
};
