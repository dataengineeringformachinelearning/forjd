import type { Meta, StoryObj } from '@storybook/angular-vite';

/**
 * Semantic type roles from `_typography.scss`.
 * Apply classes on real heading/paragraph elements in the app.
 */
const meta: Meta = {
  title: 'Foundation/Typography',
  tags: ['autodocs'],
  parameters: {
    layout: 'padded',
  },
  render: () => ({
    template: `
      <div style="display: grid; gap: 1.5rem; max-width: 36rem; text-align: left;">
        <p class="fj-brand">FORJD</p>
        <h1 class="fj-headline">Connected stack pulse</h1>
        <p class="fj-lede">
          Supporting sentence under a headline — muted, readable, capped width.
        </p>
        <h2 class="fj-panel-title">Panel title</h2>
        <p class="fj-meta">3/7 layers · id abc123</p>
        <p class="fj-muted">No data yet.</p>
        <p class="fj-error" role="alert">Something failed.</p>
      </div>
    `,
  }),
};

export default meta;
type Story = StoryObj;

export const Scale: Story = {};
