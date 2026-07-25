import type { Meta, StoryObj } from '@storybook/angular-vite';

const swatches = [
  ['--suite-bg', 'Void'],
  ['--suite-surface', 'Surface'],
  ['--suite-surface-elevated', 'Elevated'],
  ['--suite-surface-2', 'Surface 2'],
  ['--suite-border', 'Border'],
  ['--suite-border-strong', 'Border Strong'],
  ['--suite-primary', 'Primary'],
  ['--suite-success', 'Success'],
  ['--suite-warning', 'Warning'],
  ['--suite-danger', 'Danger'],
  ['--suite-gold', 'Gold'],
  ['--suite-ink', 'Ink'],
  ['--suite-ink-muted', 'Muted'],
] as const;

/**
 * Canonical suite token board — must match DEML suite-tokens.css.
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
          gap: var(--suite-space-compact);
          width: min(100%, 48rem);
          text-align: left;
        }
        .sb-token {
          display: grid;
          gap: var(--suite-space-1);
          padding: var(--suite-space-2);
          border: 1px solid var(--suite-border);
          border-radius: var(--suite-radius);
          background: var(--suite-surface);
        }
        .sb-token__swatch {
          display: block;
          height: 2.5rem;
          border-radius: var(--suite-radius);
          border: 1px solid var(--suite-border);
        }
        .sb-token code {
          display: block;
          font-family: var(--suite-font-mono);
          font-size: var(--suite-text-xs);
        }
      `,
    ],
  }),
};
