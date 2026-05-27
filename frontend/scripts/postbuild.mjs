/**
 * Runs `arx manage collectstatic --noinput` after `pnpm build`.
 *
 * Why this exists at all: `pnpm build` writes hashed assets to
 * `src/web/static/dist/` but Django serves static files from
 * `src/server/.static/` (populated by `collectstatic`). Without this
 * chain, a fresh build leaves the live page pointing at new hashes
 * the server can't serve — blank page with 404s for `index-*.js` and
 * `index-*.css`. This has bitten us at least twice.
 *
 * Why it's a Node script instead of a plain shell command in
 * package.json: CI runners don't have `uv` on PATH, and pnpm's
 * default shell isn't consistent across platforms. This script
 * detects uv up front and exits 0 with a friendly message if it
 * isn't available — so dev gets the auto-collection and CI doesn't
 * fail.
 */
import { execSync } from 'node:child_process';

function uvAvailable() {
  try {
    execSync('uv --version', { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

if (!uvAvailable()) {
  console.log(
    'postbuild: uv not on PATH — skipping collectstatic. ' +
      'This is normal in CI build runners. In dev, install uv ' +
      '(https://docs.astral.sh/uv/) for auto-collection.'
  );
  process.exit(0);
}

console.log('postbuild: running arx manage collectstatic');
execSync('uv run --project .. arx manage collectstatic --noinput', { stdio: 'inherit' });
