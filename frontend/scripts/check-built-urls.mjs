/**
 * Fails the build when a built script or stylesheet names another built file by a
 * path that starts at the site root.
 *
 * Why this exists: Django serves the build from `/static/dist/`, while the build
 * itself is made for `/`. `FrontendAppView` rewrites the paths in index.html, but a
 * URL a script builds at runtime (a lazy page's stylesheet, an imported image) or a
 * `url()` inside a stylesheet never passes through that rewrite. Such a URL has to be
 * relative to the file that holds it, which `experimental.renderBuiltUrl` in
 * vite.config.ts arranges. Without it the family page's stylesheet was requested
 * from `/assets/FamilyPage-<hash>.css`, Django answered with the app shell, and the
 * page died with "Unable to preload CSS". `vite preview` serves the build at `/`,
 * so the Playwright smoke tests cannot see this; this check can.
 *
 * It looks only for the names of files that are really in `assets/`, so a string in
 * app code such as `/api/assets/` is never mistaken for one.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

// Where `vite build` writes (build.outDir in vite.config.ts). A function, because
// under vitest's jsdom this module's URL is not a file URL and the tests pass
// their own directory.
function builtDist() {
  return fileURLToPath(new URL('../../src/web/static/dist/', import.meta.url));
}
// How many references the failure message lists before it counts the rest.
const SHOWN = 10;

function escapeForRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Returns one `{ file, reference }` entry for every root-anchored reference to a
 * built file found in the scripts and stylesheets under `<distDir>/assets`.
 */
export function findRootAnchoredReferences(distDir = builtDist()) {
  const assetsDir = join(distDir, 'assets');
  const names = readdirSync(assetsDir).filter((name) => !name.endsWith('.map'));
  if (names.length === 0) return [];

  const anyName = names.map(escapeForRegExp).join('|');
  // In a script: a string that is exactly `assets/<file>` or `/assets/<file>`.
  const inScript = new RegExp(`["'\`](/?assets/(?:${anyName}))["'\`]`, 'g');
  // In a stylesheet: `url(/assets/<file>)`, quoted or not.
  const inStylesheet = new RegExp(`url\\(\\s*["']?(/assets/(?:${anyName}))`, 'g');

  const found = [];
  for (const name of names) {
    let pattern;
    if (name.endsWith('.js')) pattern = inScript;
    else if (name.endsWith('.css')) pattern = inStylesheet;
    else continue;
    const text = readFileSync(join(assetsDir, name), 'utf8');
    for (const match of text.matchAll(pattern)) {
      found.push({ file: `assets/${name}`, reference: match[1] });
    }
  }
  return found;
}

export function checkBuiltUrls(distDir = builtDist()) {
  const found = findRootAnchoredReferences(distDir);
  if (found.length === 0) return;
  const lines = found.slice(0, SHOWN).map(({ file, reference }) => `  ${file} names ${reference}`);
  if (found.length > SHOWN) lines.push(`  and ${found.length - SHOWN} more`);
  throw new Error(
    'check-built-urls: the build names its own files by a path from the site root.\n' +
      'Django serves the build from /static/dist/, so these requests would get the app\n' +
      'shell instead of the file. Keep experimental.renderBuiltUrl in vite.config.ts\n' +
      'returning { relative: true } for scripts and stylesheets.\n' +
      lines.join('\n')
  );
}
