import type { Preview } from '@storybook/angular-vite';

/**
 * Global Storybook chrome: FJORD dark canvas.
 * Token/typography CSS comes from angular.json `styles: ["src/styles.scss"]`
 * so we do not double-import SCSS here.
 */
const preview: Preview = {
  parameters: {
    layout: 'centered',
    backgrounds: {
      default: 'void',
      values: [
        { name: 'void', value: 'var(--fj-bg, #0A0A0A)' },
        { name: 'surface', value: 'var(--fj-surface, #111111)' },
      ],
    },
    a11y: {
      test: 'todo',
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    options: {
      storySort: {
        method: 'alphabetical',
        order: ['Foundation', 'Primitives'],
      },
    },
  },
};

export default preview;
