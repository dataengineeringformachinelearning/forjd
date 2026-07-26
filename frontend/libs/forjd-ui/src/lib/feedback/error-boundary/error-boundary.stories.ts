import { signal } from '@angular/core';
import type { Meta, StoryObj } from '@storybook/angular-vite';

import { FjButton } from '../../forms/button/button';
import { FjErrorBoundary } from './error-boundary';

const meta: Meta = {
  title: 'Primitives/Error boundary',
  tags: ['autodocs'],
};
export default meta;
type Story = StoryObj;

export const Healthy: Story = {
  render: () => ({
    moduleMetadata: { imports: [FjErrorBoundary] },
    template: `
      <forjd-error-boundary>
        <p>Projected content renders while the boundary is healthy.</p>
      </forjd-error-boundary>
    `,
  }),
};

export const FailedWithRetry: Story = {
  render: () => {
    const failed = signal(true);
    return {
      props: { failed },
      moduleMetadata: { imports: [FjErrorBoundary, FjButton] },
      template: `
        <forjd-error-boundary
          [failed]="failed()"
          (failedChange)="failed.set($event)"
          title="Projection panel unavailable"
          description="Dragonfly timed out while reading stream_results."
          hint="request_id · demo"
        >
          <p>This content is hidden while failed.</p>
        </forjd-error-boundary>
      `,
    };
  },
};
