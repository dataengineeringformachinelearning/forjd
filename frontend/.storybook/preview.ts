import type { Preview } from '@storybook/angular-vite';

import '../libs/forjd-ui/src/lib/styles/_tokens.scss';
import '../libs/forjd-ui/src/lib/styles/_typography.scss';

/**
 * Global Storybook chrome: FJORD dark canvas so components look like production.
 */
const preview: Preview = {
  parameters: {
    layout: 'centered',
    backgrounds: {
      default: 'void',
      values: [
        { name: 'void', value: '#0A0A0A' },
        { name: 'surface', value: '#111111' },
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
  },
};

export default preview;
