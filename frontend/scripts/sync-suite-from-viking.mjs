#!/usr/bin/env node
/**
 * Vendor canonical suite CSS + Inter faces from the DEML sibling checkout.
 * No npm install for styles.
 *
 * Canonical: …/packages/viking-ui/src/tokens/ (+ styles/fonts/inter)
 * Usage: from frontend/ → npm run sync:suite
 */
import { copyFileSync, cpSync, existsSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const demlRoot = path.resolve(frontendDir, '../../dataengineeringformachinelearning');
const demlTokensDir = path.join(demlRoot, 'packages/viking-ui/src/tokens');
const demlFontsDir = path.join(demlRoot, 'packages/viking-ui/src/assets/fonts/inter');
const outDir = path.join(frontendDir, 'libs/forjd-ui/src/lib/styles');
const backendStatic = path.resolve(frontendDir, '../backend/static');
const publicFonts = path.join(frontendDir, 'public/fonts/inter');

const files = [
  'suite-tokens.css',
  'suite-components.css',
  'suite-landing.css',
  'suite-backend.css',
  'suite-docs.css',
  'SUITE_TOKENS.md',
  'SUITE_COMPONENTS.md',
  'SUITE_LANDING.md',
  'SUITE_BACKEND.md',
  'SUITE_DOCS.md',
];

for (const name of files) {
  const src = path.join(demlTokensDir, name);
  if (!existsSync(src)) {
    console.error('Missing', src);
    process.exit(1);
  }
  mkdirSync(outDir, { recursive: true });
  const dest = path.join(outDir, name);
  copyFileSync(src, dest);
  console.log('Synced', path.basename(src), '→', dest);
}

mkdirSync(backendStatic, { recursive: true });
for (const name of [
  'suite-tokens.css',
  'suite-components.css',
  'suite-landing.css',
  'suite-backend.css',
]) {
  copyFileSync(path.join(demlTokensDir, name), path.join(backendStatic, name));
  console.log('Synced', name, '→', path.join(backendStatic, name));
}

if (!existsSync(demlFontsDir)) {
  console.error('Missing Inter source', demlFontsDir);
  process.exit(1);
}
mkdirSync(publicFonts, { recursive: true });
cpSync(demlFontsDir, publicFonts, { recursive: true });
console.log('Synced Inter →', publicFonts);
