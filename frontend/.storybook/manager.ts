import { addons } from 'storybook/manager-api';
import { create } from 'storybook/theming';

/**
 * Pass 5 — suite manager theme (void + electric).
 * Same palette as ui.deml.app; brand title is the only product-specific field.
 */
addons.setConfig({
  theme: create({
    base: 'dark',
    brandTitle: 'Suite UI · FORJD',
    brandUrl: 'https://ui.forjd.co',
    brandTarget: '_self',
    colorPrimary: '#2176ff',
    colorSecondary: '#2176ff',
    appBg: '#0a0a0a',
    appContentBg: '#111111',
    appPreviewBg: '#0a0a0a',
    appBorderColor: '#222222',
    appBorderRadius: 8,
    textColor: '#f5f5f5',
    textMutedColor: '#aaaaaa',
    barBg: '#111111',
    barTextColor: '#aaaaaa',
    barSelectedColor: '#2176ff',
    inputBg: '#1a1a1a',
    inputBorder: '#333333',
    inputTextColor: '#f5f5f5',
    inputBorderRadius: 8,
  }),
});
