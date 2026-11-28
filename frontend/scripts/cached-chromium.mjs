/**
 * The newest headless Chromium in the shared Playwright cache (#5310).
 *
 * The devcontainer firewall can block the download a newer Playwright asks for, while an
 * older build is already there and renders the same pages. `shot.mjs` falls back to it for
 * a plain path, and `tools/shot.sh` hands it to a spec run through E2E_CHROMIUM_EXECUTABLE,
 * which `e2e.backend.config.ts` reads (#5327).
 *
 * Run directly, this prints the path, or nothing when the cache holds no build.
 */
import { existsSync, readdirSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export function cachedHeadlessShell() {
  const cache =
    process.env.PLAYWRIGHT_BROWSERS_PATH || path.join(os.homedir(), '.cache', 'ms-playwright');
  if (!existsSync(cache)) return undefined;
  const builds = readdirSync(cache)
    .filter((name) => name.startsWith('chromium_headless_shell-'))
    .sort((a, b) => Number(b.split('-')[1]) - Number(a.split('-')[1]));
  for (const build of builds) {
    const binary = path.join(
      cache,
      build,
      'chrome-headless-shell-linux64',
      'chrome-headless-shell'
    );
    if (existsSync(binary)) return binary;
  }
  return undefined;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const binary = cachedHeadlessShell();
  if (binary) console.log(binary);
}
