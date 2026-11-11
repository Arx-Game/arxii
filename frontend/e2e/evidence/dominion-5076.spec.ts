import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import { test, expect, type Page } from '@playwright/test';

/**
 * Review evidence for #5076 (slice 2 of #5069): the real Almanach pages on the
 * production bundle, every `/api/**` call answered by fixtures shaped like the
 * serializers. Nobility is macro: a kingdom page lists its duchies as Held and
 * Vassals with their people and shows no land block, developments or forces; a
 * county page carries its Hinterland and its Developments; a barony page lets staff
 * name the capacity; the ladder carries a population column.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '5076');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const REALM_ID = 5;
const KINGDOM_ID = 8;
const COUNTY_ID = 30;
const BARONY_ID = 40;
const PIROPA_ID = 9;

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

const paginated = <T>(results: T[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

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

const chain = [
  { title_id: null, name: 'Inferna', tier: 'realm' },
  { title_id: KINGDOM_ID, name: 'Inferna', tier: 'kingdom' },
];

const title = (id: number, name: string, tier: string, extra: Record<string, unknown> = {}) => ({
  title_id: id,
  name,
  tier,
  realm_id: REALM_ID,
  realm: 'Inferna',
  house_id: PIROPA_ID,
  held_by: 'House Piropa',
  holder_id: 11,
  holder: 'Hael Piropa',
  sworn_to: '',
  succession: 'Enatic gifted',
  seat: 'Perdition',
  is_claimable: false,
  chain_top_id: id,
  station: 'seated',
  pledged_liege: null,
  ...extra,
});

const books = { income_week: 12400, uncollected: 37200, treasury: 210000, streams: 3 };
const forces = [
  {
    unit_id: 1,
    name: 'Perdition Guard',
    owner: 'House Piropa',
    quality: 'veteran',
    men: 240,
    strength: 70,
    morale: 80,
    posted_here: true,
  },
];
const charter = { chartered_fiefs: [], chartered_by: [], claims: [] };

const KINGDOM_DOC = {
  title: title(KINGDOM_ID, 'Inferna', 'kingdom'),
  demesne: null,
  holdings: [],
  books,
  forces,
  vassals: [
    {
      title_id: 20,
      name: 'Vampa',
      held_by: 'House Piropa',
      demesne: 2,
      vassals: 0,
      population: 61200,
    },
    {
      title_id: 21,
      name: 'Cindermarch',
      held_by: 'House Ashen',
      demesne: 1,
      vassals: 1,
      population: 38400,
    },
    {
      title_id: 22,
      name: 'Saltreach',
      held_by: 'House Varro',
      demesne: 1,
      vassals: 0,
      population: 24900,
    },
    { title_id: 23, name: 'Hollowmere', held_by: '', demesne: 1, vassals: 0, population: 12300 },
    { title_id: 24, name: 'Brinefall', held_by: '', demesne: 1, vassals: 0, population: 9800 },
  ],
  ...charter,
  chain: [chain[0]],
};

const COUNTY_DOC = {
  title: title(COUNTY_ID, 'Inferna', 'county', { chain_top_id: KINGDOM_ID }),
  demesne: {
    domain_id: 300,
    name: 'Inferna',
    description: 'Ash plains south of Perdition, cut by the Sulphur Road.',
    hall: '',
    population: 4800,
    population_capacity: 9000,
    capacity_override: null,
    terrain: [
      { terrain: 'plain', label: 'Plain', pips: 7 },
      { terrain: 'forest', label: 'Forest', pips: 3 },
      { terrain: 'hill', label: 'Hill', pips: 2 },
    ],
    prosperity: 70,
    unrest: 10,
    defenses: 10,
  },
  holdings: [],
  books,
  forces,
  vassals: [
    {
      title_id: BARONY_ID,
      name: 'Perdition',
      held_by: 'House Piropa',
      demesne: 1,
      vassals: 0,
      population: 31000,
    },
    { title_id: 41, name: 'Cinder Gate', held_by: '', demesne: 1, vassals: 0, population: 1900 },
  ],
  ...charter,
  chain: [...chain, { title_id: 20, name: 'Vampa', tier: 'duchy' }],
};

const BARONY_DOC = {
  title: title(BARONY_ID, 'Perdition', 'barony', { chain_top_id: KINGDOM_ID }),
  demesne: {
    domain_id: 400,
    name: 'Perdition',
    description: 'The black city on the caldera rim.',
    hall: 'the Torre Accesa',
    population: 31000,
    population_capacity: 15000,
    capacity_override: null,
    terrain: [{ terrain: 'hill', label: 'Hill', pips: 1 }],
    prosperity: 75,
    unrest: 15,
    defenses: 40,
  },
  holdings: [
    {
      holding_id: 1,
      name: 'The Sulphur Docks',
      kind: 'Port',
      site: '',
      standing: 60,
      unsited: true,
    },
  ],
  books,
  forces,
  vassals: [],
  ...charter,
  chain: [
    ...chain,
    { title_id: 20, name: 'Vampa', tier: 'duchy' },
    { title_id: COUNTY_ID, name: 'Inferna', tier: 'county' },
  ],
};

const LADDER_ROW = (
  id: number,
  name: string,
  tier: string,
  level: number,
  parent: number | null,
  population: number,
  extra: Record<string, unknown> = {}
) => ({
  title_id: id,
  name,
  is_defined: name !== '',
  tier,
  level,
  parent_title_id: parent,
  house_id: PIROPA_ID,
  house_name: 'House Piropa',
  state: 'Held',
  is_seat_of: '',
  sworn_to: '',
  demesne: 1,
  vassals: 0,
  population,
  claimable: false,
  seat_domain_id: 400,
  comes_with: '',
  chain_top_id: KINGDOM_ID,
  claimant_name: '',
  station: 'seated',
  ...extra,
});

const LADDER = {
  rows: [
    LADDER_ROW(KINGDOM_ID, 'Inferna', 'kingdom', 0, null, 146600, { vassals: 4 }),
    LADDER_ROW(20, 'Vampa', 'duchy', 1, KINGDOM_ID, 61200, { comes_with: 'Inferna' }),
    LADDER_ROW(COUNTY_ID, 'Inferna', 'county', 2, 20, 37700, { comes_with: 'Inferna' }),
    LADDER_ROW(BARONY_ID, 'Perdition', 'barony', 3, COUNTY_ID, 31000, { comes_with: 'Inferna' }),
    LADDER_ROW(21, 'Cindermarch', 'duchy', 1, KINGDOM_ID, 38400, {
      house_id: 12,
      house_name: 'House Ashen',
      sworn_to: 'House Piropa (crown)',
      chain_top_id: 21,
      vassals: 1,
    }),
    LADDER_ROW(23, 'Hollowmere', 'duchy', 1, KINGDOM_ID, 12300, {
      house_id: null,
      house_name: '',
      state: 'Unclaimed',
      claimable: true,
      sworn_to: 'House Piropa (crown)',
      chain_top_id: 23,
    }),
  ],
  unclaimed_by_tier: { duchy: 1 },
};

const HOUSE_DOC = {
  family: { family_id: 4, nodes: [], parentage: [], unions: [] },
};

const dispatches: Array<Record<string, unknown>> = [];

async function mockApi(page: Page) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'archivist',
          display_name: 'Archivist',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: false,
          is_staff: true,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: 1,
          selected_entry: STAFF_CHARACTER,
        },
      });
      return;
    }
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [STAFF_CHARACTER] });
    if (p === '/api/world-builder/areas/grants/')
      return route.fulfill({ json: { is_staff: true, grants: [] } });
    if (p === '/api/world-builder/region-maps/')
      return route.fulfill({ json: [{ id: 1, name: 'Catenys' }] });
    if (p === `/api/almanach/titles/${KINGDOM_ID}/document/`)
      return route.fulfill({ json: KINGDOM_DOC });
    if (p === `/api/almanach/titles/${COUNTY_ID}/document/`)
      return route.fulfill({ json: COUNTY_DOC });
    if (p === `/api/almanach/titles/${BARONY_ID}/document/`)
      return route.fulfill({ json: BARONY_DOC });
    if (p === `/api/almanach/houses/${PIROPA_ID}/document/`)
      return route.fulfill({ json: HOUSE_DOC });
    if (p === '/api/almanach/realms/')
      return route.fulfill({ json: paginated([{ id: REALM_ID, name: 'Inferna' }]) });
    if (p === `/api/almanach/realms/${REALM_ID}/ladder/`) return route.fulfill({ json: LADDER });
    if (p === `/api/almanach/realms/${REALM_ID}/charter/`)
      return route.fulfill({
        json: {
          succession_law: null,
          particle: { born: '', taken_in: '' },
          quiddity_prompt: '',
          capital_name: 'Perdition',
        },
      });
    if (p === '/api/almanach/houses/')
      return route.fulfill({ json: paginated([{ id: PIROPA_ID, name: 'House Piropa' }]) });
    if (p === '/api/almanach/holding-kinds/')
      return route.fulfill({
        json: paginated([
          { id: 1, name: 'Port', description: '', site_kind: 'building', requires_field: false },
        ]),
      });
    if (p.startsWith('/api/actions/characters/') && p.endsWith('/dispatch/')) {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      dispatches.push(body);
      return route.fulfill({
        json: { backend: 'registry', deferred: false, message: 'ok', data: {}, success: true },
      });
    }
    const arrays = [
      '/api/magic/character-resonances/',
      '/api/precapture-consent-requests/',
      '/api/items/makeover-requests/',
      '/api/gm/summon-offers/',
      '/api/ceremonies/seance-offers/',
      '/api/ceremonies/conversion-offers/',
      '/api/magic/rituals/sessions/',
      '/api/personas/',
      '/api/world-builder/areas/unfiled-rooms/',
    ];
    if (arrays.includes(p)) return route.fulfill({ json: [] });
    if (p === '/api/interactions/') return route.fulfill({ json: { results: [], next: null } });
    return route.fulfill({ json: paginated([]) });
  });
}

test.describe('Dominion slice 2 (#5076)', () => {
  test.beforeEach(async ({ page }) => {
    dispatches.length = 0;
    await mockApi(page);
    await page.setViewportSize({ width: 1280, height: 1100 });
  });

  test('1. a kingdom page: Holdings as Held and Vassals with their people, no land block', async ({
    page,
  }) => {
    const errors = trackErrors(page);
    await page.goto(`/staff/almanach/titles/${KINGDOM_ID}`);
    await expect(page.getByRole('heading', { level: 3 })).toContainText('Inferna');
    const holdings = page
      .getByRole('heading', { name: 'Holdings' })
      .locator('xpath=following-sibling::*[1]');
    await expect(holdings.getByText('Held', { exact: true })).toBeVisible();
    await expect(holdings.getByText('Vassals', { exact: true })).toBeVisible();
    await expect(holdings.getByRole('link', { name: 'Vampa' })).toBeVisible();
    await expect(holdings.getByText('61,200')).toBeVisible();
    await expect(holdings.getByText('vacant').first()).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Hinterland' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Developments' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Forces' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Books' })).toBeVisible();
    await page.screenshot({ path: shot('1-kingdom-held-and-vassals.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('2. a county page: its Hinterland, Developments, Forces and its baronies', async ({
    page,
  }) => {
    const errors = trackErrors(page);
    await page.goto(`/staff/almanach/titles/${COUNTY_ID}`);
    const hinterland = page
      .getByRole('heading', { name: 'Hinterland' })
      .locator('xpath=following-sibling::*[1]');
    await expect(hinterland.getByText('4,800')).toBeVisible();
    await expect(hinterland.getByText('9,000')).toBeVisible();
    await expect(hinterland.getByText('plain, forest, hill')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Developments' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Forces' })).toBeVisible();
    const holdings = page
      .getByRole('heading', { name: 'Holdings' })
      .locator('xpath=following-sibling::*[1]');
    await expect(holdings.getByRole('link', { name: 'Perdition' })).toBeVisible();
    await expect(holdings.getByText('31,000')).toBeVisible();
    await page.screenshot({ path: shot('2-county-hinterland.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('3. a barony page: people and capacity, and staff name the capacity', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto(`/staff/almanach/titles/${BARONY_ID}`);
    await expect(page.getByText('31,000').first()).toBeVisible();
    await expect(page.getByText('15,000')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Hinterland' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Developments' })).toBeVisible();
    await expect(page.getByText('The Sulphur Docks')).toBeVisible();
    await page.screenshot({ path: shot('3-barony-before-set.png'), fullPage: true });
    await page.getByLabel('capacity').fill('300000');
    await page.getByRole('button', { name: 'Set' }).click();
    await expect.poll(() => dispatches.length).toBe(1);
    expect(dispatches[0]).toMatchObject({
      ref: { backend: 'registry', registry_key: 'almanach_set_capacity' },
      kwargs: { domain_id: 400, capacity: 300000 },
    });
    await page.screenshot({ path: shot('3-barony-after-set.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('4. the ladder carries a population column', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto(`/staff/almanach/realms/${REALM_ID}`);
    await expect(page.getByRole('columnheader', { name: /population/ })).toBeVisible();
    await expect(page.getByText('146,600')).toBeVisible();
    await expect(page.getByText('61,200')).toBeVisible();
    await page.screenshot({ path: shot('4-ladder-population.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});
