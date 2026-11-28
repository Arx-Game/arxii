/**
 * Full-page screenshots of the running app, one PNG per path (#5310).
 *
 * Called by tools/shot.sh (`just shot`), which starts this worktree's own server
 * first. Not a test: it asserts nothing and only records what the page shows.
 *
 *   node scripts/shot.mjs --base http://localhost:4001 --out DIR \
 *     [--account NAME --password PW] [--viewport 1440x900] /path ...
 *
 * With --account it signs in through the login page first, the way a player does.
 */
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { parseArgs } from 'node:util';

import { chromium } from '@playwright/test';

import { cachedHeadlessShell } from './cached-chromium.mjs';

const { values, positionals } = parseArgs({
  allowPositionals: true,
  options: {
    base: { type: 'string', default: 'http://localhost:4001' },
    out: { type: 'string' },
    account: { type: 'string' },
    password: { type: 'string', default: 'TestPass123!' },
    viewport: { type: 'string', default: '1440x900' },
  },
});

if (!values.out || positionals.length === 0) {
  console.error('usage: shot.mjs --out DIR [--account NAME] [--viewport WxH] /path ...');
  process.exit(1);
}
const [width, height] = values.viewport.split('x').map(Number);
if (!width || !height) {
  console.error(`bad --viewport ${values.viewport}; expected WIDTHxHEIGHT`);
  process.exit(1);
}
mkdirSync(values.out, { recursive: true });

/** A file name from a URL path: `/characters/12/sheet` -> `characters-12-sheet`. */
function fileName(urlPath, index) {
  const slug = urlPath.replace(/^\/+|\/+$/g, '').replace(/[^A-Za-z0-9]+/g, '-') || 'home';
  return `${String(index + 1).padStart(2, '0')}-${slug}.png`;
}

/** Wait for the page to stop fetching; a page that polls never goes idle, so cap it. */
async function settle(page) {
  try {
    await page.waitForLoadState('networkidle', { timeout: 10_000 });
  } catch {
    // A live socket or a poll keeps the network busy; the cap is the settle point.
  }
}

async function launch() {
  try {
    return await chromium.launch({ headless: true });
  } catch (error) {
    const fallback = cachedHeadlessShell();
    if (!String(error).includes("Executable doesn't exist") || !fallback) throw error;
    console.error(`Playwright's own Chromium is missing; using the cached ${fallback}`);
    return chromium.launch({ headless: true, executablePath: fallback });
  }
}

const browser = await launch();
let failed = false;
try {
  const page = await browser.newPage({ viewport: { width, height }, baseURL: values.base });
  if (values.account) {
    await page.goto('/login');
    await page.getByPlaceholder('Username or Email').fill(values.account);
    await page.getByPlaceholder('Password').fill(values.password);
    await page.getByRole('button', { name: 'Log In', exact: true }).click();
    await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 15_000 });
  }
  for (const [index, urlPath] of positionals.entries()) {
    const response = await page.goto(urlPath);
    await settle(page);
    const target = path.join(values.out, fileName(urlPath, index));
    await page.screenshot({ path: target, fullPage: true });
    const status = response ? response.status() : 'no response';
    console.log(`${target}  (${urlPath}, HTTP ${status})`);
    if (response && response.status() >= 400) failed = true;
  }
} finally {
  await browser.close();
}
process.exit(failed ? 2 : 0);
