import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4197: the deity edit page on the production bundle, every `/api/**`
 * call answered by fixtures shaped like the serializers. Readings: the Favored facets
 * picker as staff with a vocabulary of three; typing a spelling that resolves to nothing
 * ("Sickles") and reading the "Did you mean" answer and the Create item; creating it and
 * reading the chip; typing a spelling that resolves ("scythes") and reading that Create is
 * not offered.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4197');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const BEING_ID = 7;
const ACCOUNT = {
  id: 1,
  username: 'walk-e2e',
  display_name: 'Walk E2E',
  email: '',
  email_verified: true,
  last_login: null,
  can_create_characters: true,
  is_staff: true,
  is_gm: false,
  available_characters: [],
  pending_applications: [],
  selected_entry_id: null,
  selected_entry: null,
};
const FACETS = [
  { id: 1, name: 'Scythe' },
  { id: 2, name: 'Silk' },
  { id: 3, name: 'Wolf' },
];
const OPTIONS = {
  traditions: [{ id: 1, name: 'Church Liturgy' }],
  resonances: [{ id: 1, name: 'Saevus' }],
  facets: FACETS,
  tarot_cards: [{ id: 14, name: 'Death' }],
  organizations: [],
  beings: [{ id: 8, name: 'Calyx' }],
};
const PAGE = {
  id: BEING_ID,
  name: 'The Fleshreaper',
  description: 'Placeholder prose for shape.',
  domains: 'Carnage, Hunters',
  tradition: 1,
  is_active: true,
  quote: '',
  nicknames: ['The Gory Goddess'],
  resonances: [{ resonance: 1, resonance_name: 'Saevus', tier: 'favored' }],
  facets: [3],
  feast_days: [],
  tarot_cards: [],
  relationships: [],
  visibility: 'public',
  organization: null,
  gm_notes: '',
  resonance_pool: 0,
  codex_entry: 40,
};
const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };

async function mockEditor(page: Page) {
  const created: { id: number; name: string; description: string }[] = [];
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [] });
    if (p === `/api/worship/admin/beings/${BEING_ID}/`) return route.fulfill({ json: PAGE });
    if (p === '/api/worship/admin/beings/options/')
      return route.fulfill({ json: { ...OPTIONS, facets: [...FACETS, ...created] } });
    if (p === '/api/magic/facets/near/') {
      const name = (url.searchParams.get('name') ?? '').toLowerCase();
      const near = name.startsWith('sick') ? [{ id: 1, name: 'Scythe', description: '' }] : [];
      return route.fulfill({ json: near });
    }
    if (p === '/api/magic/facets/' && method === 'POST') {
      const body = route.request().postDataJSON() as { name: string };
      const row = { id: 10 + created.length, name: body.name, description: '' };
      created.push(row);
      return route.fulfill({ status: 201, json: { ...row, matched: false } });
    }
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (method === 'GET') return route.fulfill({ json: EMPTY_PAGE });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

test.describe('The facet picker (#4197) on the production bundle', () => {
  test('staff: near-matches, then create in the same gesture', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockEditor(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/staff/pantheon/${BEING_ID}/edit`);
    await expect(page.getByText('Favored facets')).toBeVisible();
    await expect(page.getByText('Wolf')).toBeVisible();
    await page.getByRole('button', { name: '+ Add facet' }).click();
    const input = page.getByLabel('Add facet');
    await input.fill('Sickles');
    await expect(page.getByText('Did you mean')).toBeVisible();
    await expect(page.getByText('Scythe')).toBeVisible();
    await expect(page.getByText('Create “Sickles”')).toBeVisible();
    await page.screenshot({ path: shot('01-near-and-create-1280.png') });

    await page.getByText('Create “Sickles”').click();
    await expect(page.getByText('Sickles')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Remove facet' })).toHaveCount(2);
    await page.screenshot({ path: shot('02-created-chip-1280.png') });
    expect(errors).toEqual([]);
  });

  test('a spelling that already resolves is not offered for creation', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockEditor(page);
    await page.goto(`/staff/pantheon/${BEING_ID}/edit`);
    await page.getByRole('button', { name: '+ Add facet' }).click();
    await page.getByLabel('Add facet').fill('scythes');
    await expect(page.getByText('Scythe')).toBeVisible();
    await expect(page.getByText(/^Create/)).toHaveCount(0);
    await page.screenshot({ path: shot('03-resolves-no-create-1280.png') });
  });
});
