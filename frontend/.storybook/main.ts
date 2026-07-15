import type { StorybookConfig } from '@storybook/angular-vite';

/**
 * Storybook for forjd-ui — stories live next to components under libs/forjd-ui.
 * Framework: angular-vite (Angular 22-friendly, faster than webpack).
 */
const config: StorybookConfig = {
  stories: ['../libs/forjd-ui/src/**/*.stories.@(js|jsx|mjs|ts|tsx)'],
  addons: ['@storybook/addon-docs', '@storybook/addon-a11y'],
  framework: {
    name: '@storybook/angular-vite',
    options: {
      // Skip Compodoc until we lean on JSDoc docs — keeps cold start simple.
      compodoc: false,
    },
  },
  staticDirs: [{ from: '../public', to: '/' }],
};

export default config;
