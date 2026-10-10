import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';

import {
  ALL_HOUSES,
  CHARTER,
  GENDERS,
  LAND_SHAPES,
  PIROPA_HOUSE_ID,
  REALM,
  REALM_ID,
  buildLadderRows,
  buildPiropaDocument,
} from './fixtures/inferna';
import { CLAIMABLE_TITLES, DRAFT_ID, buildDraft } from './fixtures/founder';

/**
 * Review evidence for #4206: a house's days of remembrance on the production
 * bundle, every `/api/**` call answered by fixtures shaped like the serializers.
 *
 * Three readings. The founder's House chapter carries the row editor under
 * "the house" prose: a day is added, named, dated and its story written, and
 * the draft keeps it. The Almanach document's House chapter shows the house's
 * two days with their spelled dates, a third is added, and Save dispatches
 * `almanach_edit_house` with the whole list and no spelled date. The org page's
 * house block lists each day as name, the server-spelled date, then the prose.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4206');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const OBSERVANCES = [
  {
    ic_month: 1,
    ic_day: 2,
    name: 'The Long Vigil',
    lore: 'The house keeps no fire lit from dusk to dawn, for the night the first Piropa did not.',
    when: 'Dreaming 2 (1/2)',
  },
  {
    ic_month: 10,
    ic_day: 18,
    name: 'Founding Night',
    lore: 'The first fire on the hill, and the oath sworn over it.',
    when: 'Masquing 18 (10/18)',
  },
];

const STAFF_CHARACTER = {
  id: 1,
  name: 'Archivist',
  character_id: 700,
  profile_picture_url: null,
  primary_persona_id: 700,
  active_persona_id: 700,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !/Failed to load resource/.test(msg.text())) {
      errors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => errors.push(err.message));
  return errors;
}

function userPayload(isStaff: boolean) {
  return {
    id: 1,
    username: 'e2e',
    display_name: 'E2E',
    email: '',
    email_verified: true,
    last_login: null,
    can_create_characters: !isStaff,
    is_staff: isStaff,
    is_gm: false,
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
  };
}

/** The staff document route, with the dispatch body captured for the save assertion. */
async function installStaffRoutes(page: Page, dispatched: unknown[]): Promise<void> {
  const base = buildPiropaDocument(false);
  const document = { ...base, house: { ...base.house, observances: OBSERVANCES } };
  await page.route('**/api/**', async (route) => {
    const p = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (p === '/api/user/') {
      await route.fulfill({ json: userPayload(true) });
    } else if (p === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [STAFF_CHARACTER] });
    } else if (p === '/api/almanach/realms/') {
      await route.fulfill({ json: { count: 1, next: null, previous: null, results: [REALM] } });
    } else if (p === `/api/almanach/houses/${PIROPA_HOUSE_ID}/document/`) {
      await route.fulfill({ json: document });
    } else if (p === '/api/almanach/houses/') {
      await route.fulfill({
        json: { count: ALL_HOUSES.length, next: null, previous: null, results: ALL_HOUSES },
      });
    } else if (p === '/api/character-creation/genders/') {
      await route.fulfill({ json: GENDERS });
    } else if (
      p.startsWith('/api/actions/characters/') &&
      p.endsWith('/dispatch/') &&
      method === 'POST'
    ) {
      dispatched.push(route.request().postDataJSON());
      await route.fulfill({ json: { message: 'Done.', success: true, data: null } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

/** The org page as a signed-in member reads it: the house block carries the days. */
async function installOrgRoutes(page: Page): Promise<void> {
  const org = {
    id: PIROPA_HOUSE_ID,
    name: 'House Piropa',
    description: 'The first house of the hill, and the last to leave it.',
    words: 'The Fire Keeps',
    colors: 'cinder and gold',
    sigil_description: 'A tower wreathed in flame.',
    society_name: 'Infernal Peerage',
    org_type_name: 'Noble Family',
    ranks: [],
    house: {
      family_name: 'Piropa',
      house_state: 'standing',
      demesne: 1,
      liege_name: 'The Crown',
      vassal_names: [],
      titles: [],
      domains: [],
      aspects: [{ definition: 'Quiddity', option: 'Glamour', description: 'Grandeur is due.' }],
      features: [],
      open_crises: [],
      stature: null,
      vacancies: [],
      observances: OBSERVANCES,
    },
  };
  await page.route('**/api/**', async (route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === '/api/user/') {
      await route.fulfill({ json: userPayload(false) });
    } else if (p === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [STAFF_CHARACTER] });
    } else if (p === `/api/societies/organizations/${PIROPA_HOUSE_ID}/`) {
      await route.fulfill({ json: org });
    } else if (p === `/api/societies/organizations/${PIROPA_HOUSE_ID}/feed/`) {
      await route.fulfill({ json: [] });
    } else if (p === '/api/societies/standing-declarations/') {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

/** The founder's CG draft at Lineage with the Fervor claim open (as the Almanach harness does). */
async function installFounderRoutes(page: Page): Promise<void> {
  const draft = buildDraft();
  await page.route('**/api/**', async (route) => {
    const p = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (p === '/api/user/') {
      await route.fulfill({ json: userPayload(false) });
    } else if (p === '/api/roster/entries/mine/' || p === '/api/backgrounds/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/can-create/') {
      await route.fulfill({ json: { can_create: true, reason: '' } });
    } else if (p === '/api/character-creation/explanations/') {
      await route.fulfill({ json: {} });
    } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
      await route.fulfill({ json: [draft] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      Object.assign(draft, route.request().postDataJSON() as Record<string, unknown>);
      await route.fulfill({ json: draft });
    } else if (p === '/api/character-creation/origin-templates/') {
      await route.fulfill({ json: [draft.selected_origin_template] });
    } else if (
      p === '/api/character-creation/families/' ||
      p === '/api/character-creation/vacancies/'
    ) {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/genders/') {
      await route.fulfill({ json: GENDERS });
    } else if (p === '/api/character-creation/house-titles/') {
      await route.fulfill({ json: CLAIMABLE_TITLES });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/house-claim/`) {
      await route.fulfill({ status: 404, json: { detail: 'No house claim.' } });
    } else if (p === '/api/almanach/realms/') {
      await route.fulfill({ json: { count: 1, next: null, previous: null, results: [REALM] } });
    } else if (p === `/api/almanach/realms/${REALM_ID}/ladder/`) {
      await route.fulfill({
        json: { rows: buildLadderRows(false), unclaimed_by_tier: REALM.unclaimed_by_tier },
      });
    } else if (p === `/api/almanach/realms/${REALM_ID}/charter/`) {
      await route.fulfill({ json: CHARTER });
    } else if (p === '/api/almanach/land-shapes/') {
      await route.fulfill({
        json: { count: LAND_SHAPES.length, next: null, previous: null, results: LAND_SHAPES },
      });
    } else if (p === '/api/almanach/houses/') {
      await route.fulfill({
        json: { count: ALL_HOUSES.length, next: null, previous: null, results: ALL_HOUSES },
      });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

test.describe('House observances (#4206)', () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test('the founder writes a day of remembrance on the House chapter', async ({ page }) => {
    const errors = trackErrors(page);
    await installFounderRoutes(page);
    await page.goto('/characters/create');
    await expect(page.getByText('Define a house')).toBeVisible();
    await page.getByRole('button', { name: 'Claim Fervor' }).click();
    await expect(page.locator('#founder-house-name')).toBeVisible();

    await page.locator('#founder-house-name').fill('Candela');
    await page.locator('#founder-house-words').fill('Iron and Ash');
    await page.locator('#founder-house-colors').fill('Jet and gold');
    await page.locator('#founder-house-sigil').fill('A black tower wreathed in flame.');
    await page
      .locator('#founder-house-backstory')
      .fill('A frontier duchy carved from ash and ambition.');

    await expect(page.getByText('days of remembrance')).toBeVisible();
    await page.getByRole('button', { name: 'Add a day of remembrance' }).click();
    await page.locator('#founder-house-observance-0-name').fill('Founding Night');
    await page.locator('#founder-house-observance-0-month').fill('10');
    await page.locator('#founder-house-observance-0-day').fill('18');
    await page
      .locator('#founder-house-observance-0-lore')
      .fill('The first fire on the hill, and the oath sworn over it.');
    await expect(page.locator('#founder-house-observance-0-month')).toHaveValue('10');
    await expect(page.locator('#founder-house-observance-0-day')).toHaveValue('18');

    await page.locator('#founder-house-observance-0-name').scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('01-founder-house-chapter-day-1280.png'), fullPage: true });

    // Removing the row takes its controls with it; the add door stays.
    await page.getByRole('button', { name: 'Remove day of remembrance 1' }).click();
    await expect(page.locator('#founder-house-observance-0-name')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Add a day of remembrance' })).toBeVisible();
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('the Almanach document shows, edits and saves the days', async ({ page }) => {
    const errors = trackErrors(page);
    const dispatched: unknown[] = [];
    await installStaffRoutes(page, dispatched);
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);
    await expect(page.locator('main.chapter h3').first()).toContainText('House Piropa');

    const first = page.locator(`#house-${PIROPA_HOUSE_ID}-observance-0-name`);
    await expect(first).toHaveValue('The Long Vigil');
    await expect(page.locator(`#house-${PIROPA_HOUSE_ID}-observance-1-name`)).toHaveValue(
      'Founding Night'
    );
    await expect(page.locator(`#house-${PIROPA_HOUSE_ID}-observance-1-month`)).toHaveValue('10');
    await first.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: shot('02-document-house-chapter-days-1280.png'),
      fullPage: true,
    });

    await page.getByRole('button', { name: 'Add a day of remembrance' }).click();
    await page.locator(`#house-${PIROPA_HOUSE_ID}-observance-2-name`).fill('The Ember Feast');
    await page.locator(`#house-${PIROPA_HOUSE_ID}-observance-2-month`).fill('6');
    await page.locator(`#house-${PIROPA_HOUSE_ID}-observance-2-day`).fill('21');
    await page.getByRole('button', { name: 'Save' }).click();

    await expect.poll(() => dispatched.length).toBeGreaterThan(0);
    const body = dispatched[dispatched.length - 1] as {
      action_key?: string;
      kwargs?: Record<string, unknown>;
    };
    expect(JSON.stringify(body)).toContain('almanach_edit_house');
    const kwargs = (body.kwargs ?? body) as Record<string, unknown>;
    expect(kwargs.observances).toEqual([
      { ic_month: 1, ic_day: 2, name: 'The Long Vigil', lore: OBSERVANCES[0].lore },
      { ic_month: 10, ic_day: 18, name: 'Founding Night', lore: OBSERVANCES[1].lore },
      { ic_month: 6, ic_day: 21, name: 'The Ember Feast', lore: '' },
    ]);
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('the org page lists the days with the spelled date', async ({ page }) => {
    const errors = trackErrors(page);
    await installOrgRoutes(page);
    await page.goto(`/orgs/${PIROPA_HOUSE_ID}`);
    await expect(page.getByRole('heading', { name: 'Days of Remembrance' })).toBeVisible();
    await expect(page.getByText('The Long Vigil')).toBeVisible();
    await expect(page.getByText('Dreaming 2 (1/2)')).toBeVisible();
    await expect(page.getByText('Founding Night')).toBeVisible();
    await expect(page.getByText('Masquing 18 (10/18)')).toBeVisible();
    await expect(page.getByText(OBSERVANCES[1].lore)).toBeVisible();
    await page.screenshot({ path: shot('03-org-page-days-1280.png'), fullPage: true });

    await page.setViewportSize({ width: 390, height: 1100 });
    await page.getByRole('heading', { name: 'Days of Remembrance' }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('04-org-page-days-390.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
