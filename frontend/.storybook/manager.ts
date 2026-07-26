import { addons } from 'storybook/manager-api';
import { create } from 'storybook/theming';
import roleA from '../libs/forjd-ui/src/lib/styles/suite-role-a.json';

/**
 * Pass 5 — suite manager theme (void + electric).
 * Hex from vendored suite-role-a.json (Role A lock). Storybook theming API
 * cannot consume CSS variables.
 */
addons.setConfig({
  theme: create({
    base: 'dark',
    brandTitle: 'Suite UI · FORJD',
    brandUrl: 'https://forjd.co',
    brandTarget: '_self',
    colorPrimary: roleA.primary,
    colorSecondary: roleA.primary,
    appBg: roleA.bg,
    appContentBg: roleA.surface,
    appPreviewBg: roleA.bg,
    appBorderColor: roleA.border,
    appBorderRadius: roleA.radius,
    textColor: roleA.ink,
    textMutedColor: roleA.inkMuted,
    barBg: roleA.surface,
    barTextColor: roleA.inkMuted,
    barSelectedColor: roleA.primary,
    inputBg: roleA.surface2,
    inputBorder: roleA.borderStrong,
    inputTextColor: roleA.ink,
    inputBorderRadius: roleA.radius,
  }),
});
