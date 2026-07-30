/**
 * Shared suite sync/purity path resolution + actionable stderr helpers.
 */
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendDir = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const forjdRoot = path.resolve(frontendDir, '..');

/** @param {string} message */
export function fail(message) {
  console.error(`\n✗ ${message}\n`);
  process.exit(1);
}

/** @param {string} title @param {string[]} hints */
export function failWithHints(title, hints) {
  console.error(`\n✗ ${title}`);
  for (const hint of hints) {
    console.error(`  → ${hint}`);
  }
  console.error('');
  process.exit(1);
}

/**
 * Resolve DEML checkout: FORJD_DEML_ROOT / DEML_ROOT, then current and legacy
 * sibling checkout names.
 * @returns {{ root: string, tokensDir: string, fontsDir: string, fromEnv: boolean }}
 */
export function resolveDemlPaths() {
  const fromEnv = Boolean(process.env.FORJD_DEML_ROOT || process.env.DEML_ROOT);
  const configured = process.env.FORJD_DEML_ROOT || process.env.DEML_ROOT;
  const candidates = configured
    ? [path.resolve(configured)]
    : [
        path.resolve(forjdRoot, '..', 'deml'),
        path.resolve(forjdRoot, '..', 'dataengineeringformachinelearning'),
      ];
  const root =
    candidates.find((candidate) =>
      existsSync(path.join(candidate, 'packages/viking-ui/src/tokens')),
    ) ?? candidates[0];
  return {
    root,
    tokensDir: path.join(root, 'packages/viking-ui/src/tokens'),
    fontsDir: path.join(root, 'packages/viking-ui/src/assets/fonts/inter'),
    fromEnv,
  };
}

export function demlMissingHints(deml) {
  const hints = [
    `Expected DEML at: ${deml.root}`,
    'Clone DEML beside FORJD:',
    '  cd .. && git clone <deml-remote> deml',
    'Or point at an existing checkout:',
    '  export FORJD_DEML_ROOT=/absolute/path/to/deml',
    'Then: cd frontend && npm run sync:suite',
  ];
  if (deml.fromEnv) {
    hints.unshift('FORJD_DEML_ROOT / DEML_ROOT is set but the path is invalid.');
  }
  return hints;
}

/** @returns {{ frontendDir: string, forjdRoot: string, forjdUi: string, backendStatic: string, publicFonts: string, backendFonts: string }} */
export function forjdSuiteDirs() {
  return {
    frontendDir,
    forjdRoot,
    forjdUi: path.join(frontendDir, 'libs/forjd-ui/src/lib/styles'),
    backendStatic: path.join(forjdRoot, 'backend/static'),
    publicFonts: path.join(frontendDir, 'public/fonts/inter'),
    backendFonts: path.join(forjdRoot, 'backend/static/fonts/inter'),
  };
}

/** @param {string} dir */
export function requireDir(dir, title, hints) {
  if (!existsSync(dir)) {
    failWithHints(title, hints);
  }
}
