import type { StorybookConfig } from '@storybook/angular-vite';

/**
 * Storybook for forjd-ui — suite parity with ui.deml.app (Pass 5).
 */
const config: StorybookConfig = {
  stories: ['../libs/forjd-ui/src/**/*.stories.@(js|jsx|mjs|ts|tsx)'],
  addons: ['@storybook/addon-docs', '@storybook/addon-a11y'],
  core: {
    disableTelemetry: true,
  },
  framework: {
    name: '@storybook/angular-vite',
    options: {
      compodoc: false,
    },
  },
  staticDirs: [{ from: '../public', to: '/' }],
  docs: {
    autodocs: 'tag',
  },
};

export default config;
