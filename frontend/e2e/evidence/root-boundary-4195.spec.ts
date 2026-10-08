import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4195: the root error boundary on the production bundle, with
 * the chrome made to throw. The fixture is the one that found the defect while #4193's
 * evidence was being written: every list the Layout chrome asks for on load is answered
 * with a paginated object instead of a bare list, and a chrome component throws. On
 * main that reached the root boundary, whose fallback threw `useNavigate() may be used
 * only in the context of a <Router> component.` and left a blank page. Here the card
 * renders, "Go home" loads / afresh, and no page error names the Router.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4195');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const ENTRY_ID = 1;
const SHEET_ID = 20;
const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };

const ACCOUNT = {
  id: 1,
  username: 'walk-e2e',
  display_name: 'Walk E2E',
  email: '',
  email_verified: true,
  last_login: null,
  can_create_characters: true,
  is_staff: false,
  is_gm: false,
  available_characters: [],
  pending_applications: [],
  selected_entry_id: null,
  selected_entry: null,
};
const MINE = {
  id: ENTRY_ID,
  name: 'Ilsavet du Verane',
  character_id: SHEET_ID,
  profile_picture_url: null,
  primary_persona_id: 9,
  active_persona_id: 9,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

/** Every list the chrome asks for comes back as a page object: something in the chrome throws. */
async function mockChromeCrash(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [MINE] });
    if (route.request().method() === 'GET') return route.fulfill({ json: EMPTY_PAGE });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

test.describe('The root error boundary (#4195) on the production bundle', () => {
  test('a chrome error renders the card, and Go home loads / afresh', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockChromeCrash(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Something went wrong')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Go Home' })).toBeVisible();
    expect(errors.filter((message) => message.includes('useNavigate'))).toEqual([]);
    await page.screenshot({ path: shot('01-root-fallback-1280.png') });

    const navigation = page.waitForURL(/\/$/);
    await page.getByRole('button', { name: 'Go Home' }).click();
    await navigation;
    expect(new URL(page.url()).pathname).toBe('/');
  });
});
