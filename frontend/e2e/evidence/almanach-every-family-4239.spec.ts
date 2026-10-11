import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import { test, expect, type Page } from '@playwright/test';

import {
  ALL_HOUSES,
  GENDERS,
  PIROPA_HOUSE_ID,
  REALM,
  REALM_ID,
  buildPiropaDocument,
} from './fixtures/inferna';

/**
 * Review evidence for #4239 (the Almanach for every family): the real pages on
 * the production bundle, every `/api/**` call answered by fixtures shaped like
 * the serializers. One screen per board of the approved demo: the front page,
 * a person, a house, a domain, a crime family, a family with no organization,
 * and the front page at phone width.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4239');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const KATHRYN_ID = 11;
const DUCHY_ID = 3;
const TEALE_ID = 4;
const SALTSIDE_HOUSE_ID = 12;

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
  page.on('pageerror', (err) => errors.push(String(err)));
  return errors;
}

const paginated = <T>(results: T[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

const FRONT = {
  noble: [{ kind: 'realm', id: REALM_ID, name: 'Inferna', titles: 6, held: 3, unclaimed: 2 }],
  crime: [{ kind: 'city', id: 7, name: 'Arx', families: 1, gangs: 2, crew_slots: 3 }],
  commoner: [
    { kind: 'family', id: TEALE_ID, name: 'Teale', sub: 'commoner', on_record: 9, appable: 2 },
    { kind: 'family', id: 5, name: 'Varrow', sub: 'merchant', on_record: 4, appable: 0 },
  ],
};

const person = (
  id: number,
  name: string,
  relation: string,
  tier: string,
  status: string,
  appable = false
) => ({
  id,
  name,
  relation,
  tier,
  tier_display: {
    number: { name_only: 0, functionary: 1, standing: 2, sheeted: 3 }[tier] ?? null,
    label: {
      name_only: 'Offscreen Reference',
      functionary: 'Functionary NPC',
      standing: 'Standing NPC',
      sheeted: 'Sheeted NPC',
      pc: 'Player Character',
    }[tier],
  },
  status,
  is_pc: tier === 'pc',
  sheet_id: null,
  is_appable: appable,
  family_id: 1,
});

const KATHRYN = {
  person: {
    id: KATHRYN_ID,
    name: 'Kathryn mar Katta',
    display_name: 'Kathryn mar Katta',
    gender_id: 1,
    gender: 'Woman',
    age: 24,
    tier: 'standing',
    tier_display: { number: 2, label: 'Standing NPC' },
    status: 'alive',
    record_accurate: true,
    obituary: '',
    is_pc: false,
    description: '',
  },
  family: {
    id: 1,
    name: 'Katta',
    kind: 'Noble',
    basis: 'founding',
    organization_id: PIROPA_HOUSE_ID,
  },
  kin: [
    person(12, 'Mother mar Katta', 'parent', 'name_only', 'alive'),
    person(13, 'Father mar Katta', 'parent', 'name_only', 'rip'),
    person(14, 'Sister mar Katta', 'sibling', 'name_only', 'alive', true),
  ],
  house: {
    org_id: PIROPA_HOUSE_ID,
    name: 'House Katta',
    role: 'head of house',
    rank: 1,
    household_post: '',
  },
  titles: [
    {
      title_id: DUCHY_ID,
      name: 'Duchy of Katta',
      tier: 'duchy',
      realm: 'Inferna',
      held_by: 'House Katta',
      vassals: 0,
    },
  ],
  sheet: {
    sheet_id: null,
    is_appable: false,
    name_locked: false,
    age_min: null,
    age_max: null,
    allowed_gender_ids: [],
  },
  memberships: [],
  record: { parents: 2, children: 0, siblings: 1, unions: 0, hidden_truths: 0 },
};

const DUCHY = {
  title: {
    title_id: DUCHY_ID,
    name: 'Duchy of Katta',
    tier: 'duchy',
    realm_id: REALM_ID,
    realm: 'Inferna',
    house_id: PIROPA_HOUSE_ID,
    held_by: 'House Katta',
    holder_id: KATHRYN_ID,
    holder: 'Kathryn mar Katta',
    sworn_to: 'Piropa',
    succession: 'Infernal Enatic - Durance',
    seat: 'the Katta seat',
    is_claimable: false,
    chain_top_id: DUCHY_ID,
  },
  demesne: {
    domain_id: 30,
    name: 'the Katta lands',
    description: 'PLACEHOLDER prose for shape.',
    hall: 'the Katta hall',
    population: 1000,
    prosperity: 50,
    unrest: 0,
    defenses: 10,
  },
  holdings: [
    {
      holding_id: 1,
      name: 'a quarry',
      kind: 'Quarry',
      site: 'a room in the Katta seat',
      standing: 50,
      unsited: false,
    },
    { holding_id: 2, name: 'a farm', kind: 'Farm', site: '', standing: 50, unsited: true },
  ],
  books: { income_week: 1900, uncollected: 5700, treasury: 42000, streams: 3 },
  forces: [
    {
      unit_id: 1,
      name: 'Katta household guard',
      owner: 'House Katta',
      quality: 'veteran',
      men: 120,
      strength: 70,
      morale: 80,
      posted_here: true,
    },
    {
      unit_id: 2,
      name: "a vassal's levy",
      owner: 'House Vassal',
      quality: 'levy',
      men: 300,
      strength: 35,
      morale: 50,
      posted_here: true,
    },
  ],
  vassals: [
    { title_id: 40, name: 'County of Ash', held_by: 'House Vassal', demesne: 1, vassals: 1 },
    { title_id: 41, name: '', held_by: '', demesne: 2, vassals: 0 },
    { title_id: 42, name: '', held_by: '', demesne: 2, vassals: 0 },
  ],
};

const CHAPTERS = {
  books: { income_week: 2400, uncollected: 5700, treasury: 42000, streams: 4 },
  forces: DUCHY.forces,
  openings: {
    appable: [person(14, 'Sister mar Katta', '', 'name_only', 'alive', true)],
    posts: [{ vacancy_id: 1, position: 'captain of the guard' }],
    vacant_seats: [
      { title_id: 41, name: '', held_by: '', demesne: 2, vassals: 0 },
      { title_id: 42, name: '', held_by: '', demesne: 2, vassals: 0 },
    ],
  },
  turf: null,
};

function saltsideDocument() {
  const base = buildPiropaDocument(true);
  return {
    ...base,
    house: { ...base.house, id: SALTSIDE_HOUSE_ID, name: 'the Saltside family' },
    family: { ...base.family, family_id: 6 },
    realm: { ...base.realm, demesne: [], vassals: [], holds: '' },
    lands: { count: 0, population: 0, produces: [], seat: '', baronies: [] },
    books: { income_week: 1100, uncollected: 2200, treasury: 9500, streams: 2 },
    forces: [
      {
        unit_id: 3,
        name: 'Saltside bruisers',
        owner: 'the Saltside family',
        quality: 'irregular',
        men: 40,
        strength: 30,
        morale: 60,
        posted_here: false,
      },
    ],
    openings: { appable: [], posts: [{ vacancy_id: 2, position: 'enforcer' }], vacant_seats: [] },
    turf: {
      tier: 'Crime Family',
      wards: [{ turf_id: 1, area_id: 70, name: 'Saltside', grip: 100 }],
      gangs: [
        {
          org_id: 20,
          name: 'Ashfingers',
          boss: 'Grell',
          neighborhood: 'the Wharf',
          crews: [
            {
              crew_slot_id: 1,
              name: 'The corner',
              rooms: 2,
              claimed_by: 'Wharf Rats',
              is_open: false,
            },
            { crew_slot_id: 2, name: 'Rope Walk', rooms: 1, claimed_by: '', is_open: true },
          ],
        },
        { org_id: 21, name: 'the Tidewise', boss: '', neighborhood: 'Lantern Row', crews: [] },
      ],
    },
  };
}

const TEALE = {
  family: {
    id: TEALE_ID,
    name: 'Teale',
    kind: 'Commoner',
    realm_id: REALM_ID,
    realm: 'Inferna',
    is_playable: true,
    description: '',
  },
  organization_id: null,
  tree: {
    family_id: TEALE_ID,
    nodes: [
      {
        id: 31,
        name: 'Mara Teale',
        tier: 'name_only',
        family_id: TEALE_ID,
        is_deceased: false,
        is_missing: false,
        obituary: '',
        is_appable: false,
        sheet_id: null,
        roster_entry_id: null,
        full_name: 'Mara Teale',
        short_name: 'Mara',
        gender: 'Woman',
        age: 40,
        description: '',
        believed_deceased: false,
      },
      {
        id: 32,
        name: 'Old Teale',
        tier: 'name_only',
        family_id: TEALE_ID,
        is_deceased: false,
        is_missing: true,
        obituary: '',
        is_appable: true,
        sheet_id: null,
        roster_entry_id: null,
        full_name: 'Old Teale',
        short_name: 'Old',
        gender: 'Man',
        age: 70,
        description: '',
        believed_deceased: false,
      },
    ],
    parentage: [],
    unions: [],
  },
  openings: {
    appable: [person(32, 'Old Teale', '', 'name_only', 'missing', true)],
    posts: [],
    vacant_seats: [],
  },
};

async function installRoutes(page: Page): Promise<void> {
  const piropa = {
    ...buildPiropaDocument(false),
    family: { ...buildPiropaDocument(false).family, family_id: 1 },
    ...CHAPTERS,
  };
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === '/api/user/') {
      return route.fulfill({
        json: {
          id: 1,
          username: 'staffer-e2e',
          display_name: 'Staffer',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: false,
          is_staff: true,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: null,
          selected_entry: null,
        },
      });
    }
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [STAFF_CHARACTER] });
    if (p === '/api/almanach/front/') return route.fulfill({ json: FRONT });
    if (p === '/api/almanach/search/') return route.fulfill({ json: [] });
    if (p === '/api/almanach/realms/') return route.fulfill({ json: paginated([REALM]) });
    if (p === '/api/almanach/houses/') return route.fulfill({ json: paginated(ALL_HOUSES) });
    if (p === `/api/almanach/people/${KATHRYN_ID}/document/`)
      return route.fulfill({ json: KATHRYN });
    if (p === `/api/almanach/titles/${DUCHY_ID}/document/`) return route.fulfill({ json: DUCHY });
    if (p === `/api/almanach/houses/${PIROPA_HOUSE_ID}/document/`)
      return route.fulfill({ json: piropa });
    if (p === `/api/almanach/houses/${SALTSIDE_HOUSE_ID}/document/`)
      return route.fulfill({ json: saltsideDocument() });
    if (p === `/api/almanach/families/${TEALE_ID}/document/`) return route.fulfill({ json: TEALE });
    if (p === '/api/almanach/kinds/') {
      return route.fulfill({
        json: paginated([
          { id: 1, name: 'Noble', styles_as_house: true, sort_order: 0 },
          { id: 2, name: 'Commoner', styles_as_house: false, sort_order: 1 },
        ]),
      });
    }
    if (p === '/api/almanach/templates/')
      return route.fulfill({
        json: paginated([
          {
            id: 5,
            name: 'Infernal noble house',
            realm_id: REALM_ID,
            kind_id: 1,
            tier: '',
            founds_a_crew: false,
          },
        ]),
      });
    if (p === '/api/almanach/union-kinds/')
      return route.fulfill({
        json: paginated([{ id: 1, name: 'Marriage', realm_id: REALM_ID, confers_wedlock: true }]),
      });
    if (p === '/api/almanach/titles/') return route.fulfill({ json: paginated([]) });
    if (p === '/api/character-creation/genders/') return route.fulfill({ json: GENDERS });
    if (p.startsWith('/api/actions/characters/') && p.endsWith('/dispatch/') && method === 'POST') {
      return route.fulfill({ json: { message: 'Done.', success: true, data: null } });
    }
    if (method === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

test.describe('Almanach, every family (#4239)', () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test('1 the front page', async ({ page }) => {
    const errors = trackErrors(page);
    await installRoutes(page);
    await page.goto('/staff/almanach');
    await expect(page.getByRole('heading', { name: 'Noble' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Crime' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Commoner' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create Family' })).toBeVisible();
    await page.getByRole('button', { name: 'Create Family' }).click();
    await expect(page.getByRole('form', { name: 'Create Family' })).toBeVisible();
    await page.screenshot({ path: shot('01-front-1280.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('2 a person', async ({ page }) => {
    const errors = trackErrors(page);
    await installRoutes(page);
    await page.goto(`/staff/almanach/people/${KATHRYN_ID}`);
    const heading = page.getByRole('heading', { level: 3 });
    await expect(heading).toContainText('Kathryn mar Katta');
    await expect(heading).toContainText('(Standing NPC)');
    await expect(page.getByRole('link', { name: 'Father mar Katta' })).toBeVisible();
    const rip = page.locator('.kin .gone', { hasText: '(RIP)' });
    await expect(rip).toHaveCount(1);
    const color = await rip.evaluate((el) => getComputedStyle(el).color);
    const nameColor = await page
      .locator('.kin .nm a')
      .first()
      .evaluate((el) => getComputedStyle(el).color);
    expect(color, 'the (RIP) mark reads in the muted color, not the ink').not.toBe(nameColor);
    await expect(
      page.getByRole('group', { name: 'NPC tier' }).getByRole('button', { name: '2' })
    ).toHaveAttribute('aria-pressed', 'true');
    await page.screenshot({ path: shot('02-person-1280.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('3 a house: family, titles, books and forces', async ({ page }) => {
    const errors = trackErrors(page);
    await installRoutes(page);
    await page.goto(`/staff/almanach/houses/${PIROPA_HOUSE_ID}`);
    await page.getByRole('button', { name: 'The Family' }).click();
    await expect(page.getByLabel('Add kin')).toBeVisible();
    await page.screenshot({ path: shot('03-house-family-1280.png'), fullPage: true });
    await page.getByRole('button', { name: 'Titles' }).click();
    await expect(page.getByRole('button', { name: 'Add title' })).toBeVisible();
    await page.screenshot({ path: shot('03b-house-titles-1280.png'), fullPage: true });
    await page.getByRole('button', { name: /^Books/ }).click();
    await expect(page.getByRole('heading', { name: 'Forces', exact: true })).toBeVisible();
    await page.screenshot({ path: shot('03c-house-books-1280.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('4 a domain', async ({ page }) => {
    const errors = trackErrors(page);
    await installRoutes(page);
    await page.goto(`/staff/almanach/titles/${DUCHY_ID}`);
    await expect(page.getByRole('heading', { level: 3 })).toContainText('Duchy of Katta');
    await expect(page.getByRole('heading', { name: 'Location' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Vassals' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create vassal domain' })).toBeVisible();
    await page.screenshot({ path: shot('04-domain-1280.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('5 a crime family on turf', async ({ page }) => {
    const errors = trackErrors(page);
    await installRoutes(page);
    await page.goto(`/staff/almanach/houses/${SALTSIDE_HOUSE_ID}`);
    await page.getByRole('button', { name: /Wards and gangs/ }).click();
    await expect(page.getByRole('heading', { name: 'Gangs' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Ashfingers' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Add gang' })).toBeVisible();
    await page.screenshot({ path: shot('05-crime-1280.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('6 a family with no organization', async ({ page }) => {
    const errors = trackErrors(page);
    await installRoutes(page);
    await page.goto(`/staff/almanach/families/${TEALE_ID}`);
    await expect(page.getByRole('heading', { level: 3 })).toContainText('Teale');
    await expect(page.getByRole('link', { name: 'Old Teale' }).first()).toBeVisible();
    await expect(page.locator('.kin .gone', { hasText: '(Missing)' })).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Create organization' })).toBeVisible();
    await page.screenshot({ path: shot('06-family-1280.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('7 the front page at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 400, height: 900 });
    const errors = trackErrors(page);
    await installRoutes(page);
    await page.goto('/staff/almanach');
    await expect(page.getByRole('heading', { name: 'Commoner' })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow, 'no horizontal page overflow').toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot('07-front-400.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
