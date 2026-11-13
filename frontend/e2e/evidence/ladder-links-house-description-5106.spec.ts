import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';
import { TAKEN_IN, mockCg, type Family } from './fixtures/cgLineage';

/**
 * Review evidence for #5106, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * The staff realm ladder (`/staff/almanach/realms/2`): Held by opens the house's
 * page and Sworn to opens the house or the title it names.
 *
 * The staff house page's Family chapter: the two add buttons and the dialog they
 * open read "Add family member" and "Add household member".
 *
 * Character creation at Lineage: a house's card carries the family's line of
 * introduction and a link to the house's own page, which opens beside the draft.
 * That page (`/families/4`) is where the house's description, written on its
 * staff page, reads in full.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '5106');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const REALM_ID = 2;
const KATTA = 7;
const VALEWEEP = 12;
const EMPIRE = 100;
const VESTYR = 110;
const VESTYR_COUNTY = 111;

const CHARACTER = {
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
const ACCOUNT = {
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
};

const row = (fields: Record<string, unknown>) => ({
  is_defined: true,
  level: 50,
  parent_title_id: null,
  house_id: null,
  house_name: '',
  state: 'Unclaimed',
  is_seat_of: '',
  sworn_to: '',
  sworn_to_house_id: null,
  sworn_to_title_id: null,
  demesne: 0,
  vassals: 0,
  population: 1000,
  claimable: false,
  seat_domain_id: null,
  comes_with: '',
  claimant_name: '',
  station: 'seated',
  ...fields,
});
/** The empire held by Katta; a duchy held by Valeweep and sworn to Katta's crown;
 * the duchy's own county, sworn to the duchy. */
const LADDER = {
  rows: [
    row({
      title_id: EMPIRE,
      name: 'Umbral Empire',
      tier: 'empire',
      level: 60,
      house_id: KATTA,
      house_name: 'Katta',
      state: 'Held',
      vassals: 1,
      population: 9000,
      chain_top_id: EMPIRE,
    }),
    row({
      title_id: VESTYR,
      name: 'Vestyr',
      tier: 'duchy',
      level: 56,
      parent_title_id: EMPIRE,
      house_id: VALEWEEP,
      house_name: 'Valeweep',
      state: 'Held',
      sworn_to: 'Katta (crown)',
      sworn_to_house_id: KATTA,
      demesne: 1,
      population: 3000,
      chain_top_id: VESTYR,
    }),
    row({
      title_id: VESTYR_COUNTY,
      name: 'Greywater',
      tier: 'county',
      level: 53,
      parent_title_id: VESTYR,
      house_id: VALEWEEP,
      house_name: 'Valeweep',
      state: 'Held',
      sworn_to: 'Vestyr',
      sworn_to_title_id: VESTYR,
      comes_with: 'Vestyr',
      chain_top_id: VESTYR,
    }),
  ],
  unclaimed_by_tier: {},
};

const houseDocument = (id: number, name: string, description = '') => ({
  house: {
    id,
    name,
    description,
    words: '',
    colors: '',
    sigil_description: '',
    house_state: 'standing',
    published_at: null,
    particle: { born: 'mar', taken_in: 'mal' },
    default_succession_law: null,
    patron: null,
    facets: [],
    charter_questions: [],
    features: [],
    offices: [],
    observances: [],
  },
  family: { family_id: 4, nodes: [], parentage: [], unions: [] },
  household: [],
  realm: {
    sworn_to: '',
    obligation_pct: null,
    holds: 'Umbral Empire',
    demesne: [],
    vassals: [],
    realm_id: REALM_ID,
    default_tithe_pct: 10,
    realm_theme: '',
  },
  lands: { count: 0, population: 0, produces: [], seat: '', baronies: [] },
  estate: [],
  books: { income_week: 0, uncollected: 0, treasury: 0, streams: 0 },
  forces: [],
  openings: { appable: [], posts: [], vacant_seats: [] },
  turf: null,
});

/** House Katta's description as staff wrote it on the house's page: the house
 * document carries it, and the family read gives the same text (#5106's rule). */
const KATTA_LORE = [
  "Commoners often confuse the House words of Katta, as 'First in the Shadow' is used to reference the ancient roots of the great house of Umbros. At the end of the 8th age, when the world rose against the dark, the first of the line stood where the shadow was deepest and did not move. The house has told the story ever since, in halls where the lamps are kept low, and no child of the line is allowed to forget which wall their ancestor held.",
  'The house keeps its own counsel. Its vassals learn early that a promise from Katta is kept, and that a silence from Katta is a promise too.',
  'A red dragon breaking chains in its teeth, on a black field, hangs over every gate the house holds.',
].join('\n\n');

const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };
const BARE_ARRAYS = [
  '/api/magic/character-resonances/',
  '/api/precapture-consent-requests/',
  '/api/items/makeover-requests/',
  '/api/gm/summon-offers/',
  '/api/ceremonies/seance-offers/',
  '/api/ceremonies/conversion-offers/',
  '/api/magic/rituals/sessions/',
  '/api/personas/',
  '/api/character-creation/genders/',
];

async function mockStaff(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [CHARACTER] });
    if (p === '/api/almanach/realms/') {
      return route.fulfill({
        json: { ...EMPTY_PAGE, count: 1, results: [{ id: REALM_ID, name: 'Umbros' }] },
      });
    }
    if (p === `/api/almanach/realms/${REALM_ID}/ladder/`) return route.fulfill({ json: LADDER });
    if (p === `/api/almanach/realms/${REALM_ID}/charter/`) {
      return route.fulfill({
        json: {
          succession_law: null,
          particle: { born: 'mar', taken_in: 'mal' },
          quiddity_prompt: '',
          capital_name: '',
        },
      });
    }
    if (p === `/api/almanach/houses/${KATTA}/document/`) {
      return route.fulfill({ json: houseDocument(KATTA, 'Katta', KATTA_LORE) });
    }
    if (p === `/api/almanach/houses/${VALEWEEP}/document/`) {
      return route.fulfill({ json: houseDocument(VALEWEEP, 'Valeweep') });
    }
    if (BARE_ARRAYS.includes(p)) return route.fulfill({ json: [] });
    if (route.request().method() === 'GET') return route.fulfill({ json: EMPTY_PAGE });
    return route.fulfill({ json: { message: 'Done.', success: true, data: null } });
  });
}

/** The family row's line of introduction: what a card in character creation shows. */
const KATTA_INTRO = 'The imperial house of Umbros, first in the shadow.';
const NOBLE = { id: 2, name: 'Noble', styles_as_house: true };
const KATTA_FAMILY: Family = {
  id: 4,
  name: 'Katta',
  kind: NOBLE,
  influence: 0,
  standing: null,
  description: KATTA_INTRO,
  born_particle: 'mar',
  taken_in_particle: 'mal',
  inherited: { facets: [], features: [], liege_name: '' },
};
const VALEWEEP_FAMILY: Family = {
  ...KATTA_FAMILY,
  id: 5,
  name: 'Valeweep',
  description: 'A ducal house of the northern marches.',
};

/** `/api/roster/families/4/tree/`: the family row with its short line, and the
 * house as a gate shows it, carrying the description written on its staff page. */
const FAMILY_TREE = {
  family: { ...KATTA_FAMILY, is_playable: true, origin_realm: null },
  house: {
    id: KATTA,
    name: 'House Katta',
    description: KATTA_LORE,
    words: 'First in the Shadow',
    colors: 'red and black',
    sigil_description: 'a red dragon breaking chains in its teeth',
    org_type_name: 'noble_family',
    society_name: 'The Umbral Court',
    family_id: 4,
  },
  realm_name: 'Umbros',
  nodes: [],
  parentage: [],
  unions: [],
};

test.describe('#5106 on the production bundle', () => {
  test('the staff ladder opens the house in Held by and what a rung is sworn to', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockStaff(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/staff/almanach/realms/${REALM_ID}`);
    const ladder = page.locator('table.lad');
    await expect(ladder).toContainText('Umbral Empire');

    // Held by: each house's own page.
    const heldByKatta = ladder.locator('td.held').getByRole('link', { name: 'Katta', exact: true });
    await expect(heldByKatta).toHaveAttribute('href', `/staff/almanach/houses/${KATTA}`);
    await expect(
      ladder.locator('td.held').getByRole('link', { name: 'Valeweep', exact: true }).first()
    ).toHaveAttribute('href', `/staff/almanach/houses/${VALEWEEP}`);
    // Sworn to: a house where the name is a house, a title where it is a title.
    await expect(ladder.getByRole('link', { name: 'Katta (crown)', exact: true })).toHaveAttribute(
      'href',
      `/staff/almanach/houses/${KATTA}`
    );
    await ladder.getByRole('button', { name: 'Expand Vestyr' }).click();
    const duchyRow = ladder.locator('tr', { hasText: 'Greywater' });
    await expect(duchyRow.getByRole('link', { name: 'Vestyr', exact: true })).toHaveAttribute(
      'href',
      `/staff/almanach/titles/${VESTYR}`
    );

    // A linked cell says so under the pointer, the way a rung's name does.
    await heldByKatta.hover();
    await expect(heldByKatta).toHaveCSS('text-decoration-line', 'underline');

    await page.screenshot({ path: shot('1-ladder-links.png'), fullPage: true });

    // The click lands on Katta's house page.
    await heldByKatta.click();
    await expect(page).toHaveURL(new RegExp(`/staff/almanach/houses/${KATTA}$`));
    await expect(page.locator('main.chapter h3').first()).toContainText('House Katta');
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('the family page adds a family member or a household member', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockStaff(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/staff/almanach/houses/${KATTA}`);
    await page.getByRole('button', { name: 'The Family', exact: true }).click();

    // The house's own page holds the description character creation shows below.
    await page.getByRole('button', { name: 'The House', exact: true }).click();
    await expect(page.locator(`#house-description-${KATTA}`)).toHaveValue(KATTA_LORE);
    await page.screenshot({ path: shot('5-house-page-description.png'), fullPage: true });
    await page.getByRole('button', { name: 'The Family', exact: true }).click();

    const family = page.getByRole('button', { name: 'Add family member', exact: true });
    const household = page.getByRole('button', { name: 'Add household member', exact: true });
    await expect(family).toBeVisible();
    await expect(household).toBeVisible();
    await expect(page.getByText('a child · a spouse')).toHaveCount(0);
    await expect(page.getByText('a person of the household')).toHaveCount(0);
    await page.screenshot({ path: shot('2-family-add-buttons.png'), fullPage: true });

    await family.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Add family member' })).toBeVisible();
    await page.keyboard.press('Escape');
    await household.click();
    await expect(dialog.getByRole('heading', { name: 'Add household member' })).toBeVisible();
    await page.waitForTimeout(600);
    await page.screenshot({ path: shot('3-add-household-dialog.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test("character creation: a house's card is a line of introduction and a way to its page", async ({
    page,
    context,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1500 });
    await mockCg(page, TAKEN_IN, {
      families: [KATTA_FAMILY, VALEWEEP_FAMILY],
      family: KATTA_FAMILY,
    });
    const writes: string[] = [];
    page.on('request', (request) => {
      if (request.method() !== 'GET') writes.push(`${request.method()} ${request.url()}`);
    });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    const card = page.locator('.cursor-pointer', { hasText: 'Katta' }).first();
    await expect(card).toContainText(KATTA_INTRO);
    // The card holds the introduction only: none of the house's long description.
    await expect(page.getByText('Commoners often confuse')).toHaveCount(0);
    const link = card.getByRole('link', { name: 'House page' });
    await expect(link).toHaveAttribute('href', '/families/4');
    await expect(link).toHaveAttribute('target', '_blank');
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot('4-cg-house-card.png'), fullPage: true });

    // The link opens the house's page beside character creation; the draft stays
    // where it was and the click picks nothing.
    await context.route('**/api/**', async (route: Route) => {
      const p = new URL(route.request().url()).pathname;
      if (p === '/api/roster/families/4/tree/') return route.fulfill({ json: FAMILY_TREE });
      if (p === '/api/roster/families/4/slots/') {
        return route.fulfill({ json: { slots: [], pools: [] } });
      }
      // The new tab is a signed-in player's: the account, then empty chrome reads.
      if (p === '/api/user/') {
        return route.fulfill({ json: { ...ACCOUNT, is_staff: false, username: 'player-e2e' } });
      }
      if (p === '/api/roster/entries/mine/' || BARE_ARRAYS.includes(p)) {
        return route.fulfill({ json: [] });
      }
      return route.fulfill({ json: EMPTY_PAGE });
    });
    writes.length = 0; // the stage's own loading writes are done; count from the click
    const [housePage] = await Promise.all([context.waitForEvent('page'), link.click()]);
    await housePage.waitForLoadState();
    await expect(housePage).toHaveURL(/\/families\/4$/);
    await expect(housePage.getByRole('heading', { level: 1, name: 'House Katta' })).toBeVisible();
    // The house's description, as written on its staff page, paragraph for paragraph.
    const description = housePage.getByRole('region', { name: 'Description' });
    expect(await description.locator('p').allTextContents()).toEqual(KATTA_LORE.split('\n\n'));
    await housePage.screenshot({ path: shot('7-house-player-page.png'), fullPage: true });

    await expect(page).toHaveURL(/\/characters\/create$/);
    await expect(page.getByLabel('An established family')).toBeChecked();
    expect(writes, 'following the link writes nothing to the draft').toEqual([]);
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
