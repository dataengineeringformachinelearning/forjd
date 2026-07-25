import type { Meta, StoryObj } from '@storybook/angular-vite';

const swatches = [
  ['--fj-bg', 'Void'],
  ['--fj-surface', 'Surface'],
  ['--fj-surface-2', 'Surface 2'],
  ['--fj-border', 'Border'],
  ['--fj-primary', 'Primary'],
  ['--fj-success', 'Success'],
  ['--fj-warning', 'Warning'],
  ['--fj-danger', 'Danger'],
  ['--fj-gold', 'Gold'],
  ['--fj-text', 'Text'],
  ['--fj-text-muted', 'Muted'],
] as const;

/**
 * Foundation token board — Chromatic baseline for the FJORD palette.
 */
const meta: Meta = {
  title: 'Foundation/Tokens',
  tags: ['autodocs'],
};

export default meta;

export const Palette: StoryObj = {
  render: () => ({
    template: `
      <div class="sb-tokens">
        ${swatches
          .map(
            ([token, label]) => `
          <div class="sb-token">
            <span class="sb-token__swatch" style="background: var(${token})"></span>
            <div>
              <strong class="fj-meta">${label}</strong>
              <code class="fj-muted">${token}</code>
            </div>
          </div>
        `,
          )
          .join('')}
      </div>
    `,
    styles: [
      `
        .sb-tokens {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
          gap: var(--fj-space-3);
          width: min(100%, 48rem);
          text-align: left;
        }
        .sb-token {
          display: grid;
          gap: var(--fj-space-2);
          padding: var(--fj-space-3);
          border: 1px solid var(--fj-border);
          border-radius: var(--fj-radius);
          background: var(--fj-surface);
        }
        .sb-token__swatch {
          display: block;
          height: 2.5rem;
          border-radius: var(--fj-radius);
          border: 1px solid var(--fj-border);
        }
        .sb-token code {
          display: block;
          font-family: var(--fj-font-mono);
          font-size: var(--fj-text-xs);
        }
      `,
    ],
  }),
};
