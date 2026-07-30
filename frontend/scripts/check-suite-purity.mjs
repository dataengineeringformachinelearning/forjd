#!/usr/bin/env node
/**
 * FORJD suite purity — forjd-ui and backend/static must match each other
 * (and DEML sibling when present). Run after npm run sync:suite.
 *
 * DEML check path: FORJD_DEML_ROOT / DEML_ROOT, else sibling clone.
 */
import { createHash } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import { forjdSuiteDirs, resolveDemlPaths } from './suite-paths.mjs';

const dirs = forjdSuiteDirs();
const deml = resolveDemlPaths();

const suiteUiFiles = [
  'suite-tokens.css',
  'suite-components.css',
  'suite-landing.css',
  'suite-backend.css',
  'suite-docs.css',
  'suite-apidocs.css',
];
const suiteBackendFiles = [
  'suite-tokens.css',
  'suite-components.css',
  'suite-landing.css',
  'suite-backend.css',
  'suite-apidocs.css',
];

const failures = [];

/** @param {string} file */
function sha(file) {
  return createHash('sha256').update(readFileSync(file)).digest('hex');
}

for (const name of suiteBackendFiles) {
  const ui = path.join(dirs.forjdUi, name);
  const be = path.join(dirs.backendStatic, name);
  if (!existsSync(ui)) {
    failures.push(`forjd-ui missing ${name}`);
    continue;
  }
  if (!existsSync(be)) {
    failures.push(`backend/static missing ${name}`);
    continue;
  }
  if (sha(ui) !== sha(be)) {
    failures.push(`Suite drift: ${name} forjd-ui ≠ backend/static`);
  }
}

const demlPresent = existsSync(deml.tokensDir);
if (demlPresent) {
  for (const name of suiteUiFiles) {
    const demlFile = path.join(deml.tokensDir, name);
    const ui = path.join(dirs.forjdUi, name);
    if (!existsSync(demlFile) || !existsSync(ui)) continue;
    if (sha(demlFile) !== sha(ui)) {
      failures.push(`Suite drift: ${name} DEML ≠ forjd-ui`);
    }
  }
}

const banned = [
  'frontend/libs/forjd-ui/src/lib/styles/_typography.scss',
  'frontend/libs/forjd-ui/src/lib/data/status-list/status-list.scss',
  'frontend/src/app/landing/landing.scss',
];
for (const rel of banned) {
  if (existsSync(path.join(dirs.forjdRoot, rel))) {
    failures.push(`Leftover theme file: ${rel}`);
  }
}

// Durable API docs: self-hosted vendor + no CDN in HTML shells.
const vendorRequired = [
  'backend/static/vendor/swagger-ui-dist/swagger-ui-bundle.js',
  'backend/static/vendor/swagger-ui-dist/swagger-ui.css',
  'backend/static/vendor/redoc/redoc.standalone.js',
  'backend/static/docs-swagger-init.js',
  'backend/static/suite-apidocs.css',
  'backend/static/forjd-apidocs.css',
];
for (const rel of vendorRequired) {
  if (!existsSync(path.join(dirs.forjdRoot, rel))) {
    failures.push(`Missing self-hosted apidocs asset: ${rel}`);
  }
}
for (const rel of ['backend/app/core/docs_page.py', 'backend/app/core/redoc_page.py']) {
  const src = readFileSync(path.join(dirs.forjdRoot, rel), 'utf8');
  if (/cdn\.jsdelivr\.net\/npm\/(swagger-ui|redoc)/i.test(src)) {
    failures.push(`CDN apidocs dependency in ${rel} — use /static/vendor/`);
  }
  if (rel.endsWith('docs_page.py') && src.includes('<style>')) {
    failures.push(`${rel} still has inline <style> — use suite-apidocs.css`);
  }
}

if (failures.length) {
  console.error('\n✗ FORJD suite purity FAILED\n');
  for (const f of failures) console.error(' -', f);
  console.error('\nFix:');
  console.error('  cd frontend && npm run sync:suite && npm run suite:purity');
  if (!demlPresent) {
    console.error('\nNote: DEML sibling not found — only forjd-ui ↔ backend/static was checked.');
    console.error(`  Looked for tokens at: ${deml.tokensDir}`);
    console.error('  Set FORJD_DEML_ROOT to include the DEML lockstep check.');
  } else {
    console.error(`\nDEML tokens: ${deml.tokensDir}`);
  }
  console.error('');
  process.exit(1);
}

const demlNote = demlPresent
  ? `DEML lockstep OK (${deml.tokensDir})`
  : 'DEML sibling absent (skipped; set FORJD_DEML_ROOT to enable)';
console.log(`✓ FORJD suite purity OK — forjd-ui ↔ backend/static; ${demlNote}`);
