#!/usr/bin/env node
/**
 * Local frontend preflight — Node engines + common serve pitfalls.
 * Exit 0 with warnings; exit 1 only for hard blockers (Node too old).
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

function parseMajorMinor(version) {
  const m = String(version)
    .replace(/^v/, '')
    .match(/^(\d+)\.(\d+)/);
  if (!m) return null;
  return { major: Number(m[1]), minor: Number(m[2]) };
}

function nodeOk(version) {
  const v = parseMajorMinor(version);
  if (!v) return false;
  // Matches package.json engines: ^22.22.3 || ^24.15.0 || ^26.0.0
  if (v.major === 22) return v.minor >= 22;
  if (v.major === 24) return v.minor >= 15;
  if (v.major >= 26) return true;
  return false;
}

const warnings = [];
const errors = [];

const nodeVersion = process.versions.node;
if (!nodeOk(nodeVersion)) {
  errors.push(
    `Node ${nodeVersion} is below the Angular 22 CLI floor.`,
    'Need Node ^22.22.3 || ^24.15.0 || ^26.',
    'Fix: nvm install 24 && nvm use 24  (see frontend/.nvmrc)',
    'Cloud VMs: put $HOME/.nvm/versions/node/v24.*/bin ahead of /exec-daemon on PATH.',
  );
}

if (!existsSync(path.join(frontendDir, 'node_modules', '@angular', 'cli'))) {
  errors.push(
    'node_modules looks incomplete (@angular/cli missing).',
    'Fix: cd frontend && npm install',
  );
}

const suiteCss = path.join(frontendDir, 'libs/forjd-ui/src/lib/styles/suite-tokens.css');
if (!existsSync(suiteCss)) {
  warnings.push(
    'suite-tokens.css missing — landing styles will be incomplete.',
    'Fix: cd frontend && npm run sync:suite  (needs DEML sibling or FORJD_DEML_ROOT)',
  );
}

if (process.env.FORJD_POLL) {
  const poll = Number(process.env.FORJD_POLL);
  if (!Number.isFinite(poll) || poll < 100) {
    warnings.push('FORJD_POLL should be milliseconds ≥ 100 (e.g. FORJD_POLL=1000).');
  } else {
    console.log(`ℹ File polling enabled (FORJD_POLL=${poll}ms) — use when EMFILE / flaky HMR.`);
  }
}

if (errors.length) {
  console.error('\n✗ Frontend preflight failed\n');
  for (const line of errors) console.error(`  → ${line}`);
  console.error('\nSee docs/DEV.md\n');
  process.exit(1);
}

if (warnings.length) {
  console.warn('\n⚠ Frontend preflight warnings\n');
  for (const line of warnings) console.warn(`  → ${line}`);
  console.warn('');
} else {
  console.log(`✓ Frontend preflight OK (Node ${nodeVersion})`);
}
