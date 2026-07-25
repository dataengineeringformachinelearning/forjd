import {
  componentWrapperDecorator,
  type Preview,
} from '@storybook/angular-vite';

import '../libs/forjd-ui/src/lib/styles/suite-tokens.css';
import '../libs/forjd-ui/src/lib/styles/suite-components.css';
import '../libs/forjd-ui/src/lib/styles/suite-docs.css';
import './storybook.css';

/**
 * Pass 5 — same Foundation/Primitives taxonomy + suite story chrome as ui.deml.app.
 */
const preview: Preview = {
  parameters: {
    layout: 'fullscreen',
    backgrounds: {
      default: 'void',
      values: [
        { name: 'void', value: 'var(--suite-bg)' },
        { name: 'surface', value: 'var(--suite-surface)' },
        { name: 'elevated', value: 'var(--suite-surface-elevated)' },
      ],
    },
    a11y: {
      test: 'todo',
    },
    controls: {
      expanded: true,
      sort: 'requiredFirst',
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    docs: {
      story: {
        inline: false,
      },
    },
    options: {
      storySort: {
        method: 'alphabetical',
        order: ['Foundation', 'Primitives', 'Product'],
      },
    },
    chromatic: {
      viewports: [375, 768, 1280],
    },
  },
  tags: ['autodocs'],
  decorators: [
    componentWrapperDecorator(
      (story) =>
        `<div class="suite-story-shell fj-story-shell" data-theme="dark"><div class="suite-story-panel fj-story-panel">${story}</div></div>`,
    ),
  ],
};

export default preview;
