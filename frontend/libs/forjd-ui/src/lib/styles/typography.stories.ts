import type { Meta, StoryObj } from '@storybook/angular-vite';

/**
 * Semantic type roles from suite-landing.css (`.suite-*` / `.fj-*`).
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
      <div class="suite-stack fj-stack" style="max-width: var(--suite-readable-max); text-align: left;">
        <p class="fj-brand suite-landing-brand">FORJD</p>
        <h1 class="fj-headline suite-landing-headline">Universal secure streaming</h1>
        <p class="fj-lede suite-landing-lede">
          Supporting sentence under a headline — muted, readable, capped width.
        </p>
        <h2 class="suite-panel-title fj-panel-title">Panel title</h2>
        <p class="suite-meta fj-meta">3/7 layers · id abc123</p>
        <p class="suite-muted fj-muted">No data yet.</p>
        <p class="suite-error-text fj-error" role="alert">Something failed.</p>
      </div>
    `,
  }),
};

export default meta;
type Story = StoryObj;

export const Scale: Story = {};
