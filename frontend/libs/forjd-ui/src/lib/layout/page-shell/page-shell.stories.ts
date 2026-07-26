import type { Meta, StoryObj } from '@storybook/angular-vite';
import { FjPageShell, FjSection, FjStack } from './page-shell';
import { FjPanel } from '../panel/panel';

const meta: Meta = {
  title: 'Primitives/PageShell',
  tags: ['autodocs'],
};

export default meta;

export const Shell: StoryObj = {
  render: () => ({
    moduleMetadata: {
      imports: [FjPageShell, FjSection, FjStack, FjPanel],
    },
    template: `
      <forjd-page-shell style="width: min(100%, 40rem); text-align: left">
        <forjd-stack>
          <forjd-section>
            <p class="fj-panel-title">Section</p>
            <forjd-panel variant="card" title="Card">
              <p class="fj-meta">Same shell rhythm as deml.app.</p>
            </forjd-panel>
          </forjd-section>
        </forjd-stack>
      </forjd-page-shell>
    `,
  }),
};
