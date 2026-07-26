#!/usr/bin/env node
/**
 * Vendor canonical suite CSS + Inter faces from the DEML sibling checkout.
 * No npm install for styles.
 *
 * Canonical: …/packages/viking-ui/src/tokens/ (+ styles/fonts/inter)
 * Usage: from frontend/ → npm run sync:suite
 *
 * Override checkout: FORJD_DEML_ROOT or DEML_ROOT.
 *
 * Backend: suite-fonts.css is rewritten so @font-face points at
 * /static/fonts/inter/* (API serves only /static, not /fonts).
 */
import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

import {
  demlMissingHints,
  failWithHints,
  forjdSuiteDirs,
  requireDir,
  resolveDemlPaths,
} from './suite-paths.mjs';

const deml = resolveDemlPaths();
const dirs = forjdSuiteDirs();

requireDir(
  deml.tokensDir,
  'Cannot sync suite — DEML tokens directory not found.',
  demlMissingHints(deml),
);

const files = [
  'suite-fonts.css',
  'suite-tokens.css',
  'suite-components.css',
  'suite-landing.css',
  'suite-backend.css',
  'suite-docs.css',
  'suite-apidocs.css',
  'SUITE_TOKENS.md',
  'SUITE_COMPONENTS.md',
  'SUITE_LANDING.md',
  'SUITE_BACKEND.md',
  'SUITE_DOCS.md',
  'SUITE_APIDOCS.md',
  'suite-role-a.json',
];

const missing = files.filter((name) => !existsSync(path.join(deml.tokensDir, name)));
if (missing.length) {
  failWithHints('DEML tokens directory is incomplete.', [
    `Missing: ${missing.join(', ')}`,
    `Looked in: ${deml.tokensDir}`,
    'Pull latest DEML and rebuild Viking suite tokens if needed.',
    'Then: cd frontend && npm run sync:suite',
  ]);
}

mkdirSync(dirs.forjdUi, { recursive: true });
for (const name of files) {
  const src = path.join(deml.tokensDir, name);
  const dest = path.join(dirs.forjdUi, name);
  copyFileSync(src, dest);
  console.log('Synced', name, '→', dest);
}

mkdirSync(dirs.backendStatic, { recursive: true });
for (const name of [
  'suite-tokens.css',
  'suite-components.css',
  'suite-landing.css',
  'suite-backend.css',
  'suite-apidocs.css',
]) {
  copyFileSync(path.join(deml.tokensDir, name), path.join(dirs.backendStatic, name));
  console.log('Synced', name, '→', path.join(dirs.backendStatic, name));
}

// Backend fonts: rewrite url("/fonts/inter/…") → /static/fonts/inter/… for API mount
const fontsSrc = path.join(deml.tokensDir, 'suite-fonts.css');
const fontsBackend = readFileSync(fontsSrc, 'utf8').replace(
  /url\((["']?)\/fonts\/inter\//g,
  'url($1/static/fonts/inter/',
);
writeFileSync(path.join(dirs.backendStatic, 'suite-fonts.css'), fontsBackend);
console.log(
  'Synced suite-fonts.css (backend paths) →',
  path.join(dirs.backendStatic, 'suite-fonts.css'),
);

requireDir(deml.fontsDir, 'Cannot sync Inter fonts — DEML font directory not found.', [
  ...demlMissingHints(deml),
  `Expected fonts at: ${deml.fontsDir}`,
]);

mkdirSync(dirs.publicFonts, { recursive: true });
cpSync(deml.fontsDir, dirs.publicFonts, { recursive: true });
console.log('Synced Inter →', dirs.publicFonts);

mkdirSync(dirs.backendFonts, { recursive: true });
cpSync(deml.fontsDir, dirs.backendFonts, { recursive: true });
console.log('Synced Inter →', dirs.backendFonts);

console.log('\n✓ Suite sync complete. Verify with: npm run suite:purity\n');
