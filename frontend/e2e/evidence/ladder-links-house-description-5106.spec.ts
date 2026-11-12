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
 * Character creation at Lineage: a house's card shows the opening of the house's
 * own description, and the whole of it reads below, in its paragraphs, once the
 * house is picked.
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

const houseDocument = (id: number, name: string) => ({
  house: {
    id,
    name,
    description: '',
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
      return route.fulfill({ json: houseDocument(KATTA, 'Katta') });
    }
    if (p === `/api/almanach/houses/${VALEWEEP}/document/`) {
      return route.fulfill({ json: houseDocument(VALEWEEP, 'Valeweep') });
    }
    if (BARE_ARRAYS.includes(p)) return route.fulfill({ json: [] });
    if (route.request().method() === 'GET') return route.fulfill({ json: EMPTY_PAGE });
    return route.fulfill({ json: { message: 'Done.', success: true, data: null } });
  });
}

const KATTA_LORE = [
  "Commoners often confuse the House words of Katta, as 'First in the Shadow' is used to reference the ancient roots of the great house of Umbros. At the end of the 8th age, when the world rose against the dark, the first of the line stood where the shadow was deepest and did not move. The house has told the story ever since, in halls where the lamps are kept low, and no child of the line is allowed to forget which wall their ancestor held.",
  'The house keeps its own counsel. Its vassals learn early that a promise from Katta is kept, and that a silence from Katta is a promise too.',
  'A red dragon breaking chains in its teeth, on a black field, hangs over every gate the house holds.',
].join('\n\n');
const NOBLE = { id: 2, name: 'Noble', styles_as_house: true };
const KATTA_FAMILY: Family = {
  id: 4,
  name: 'Katta',
  kind: NOBLE,
  influence: 0,
  standing: null,
  description: KATTA_LORE,
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

  test("character creation shows a house's own description: the opening on its card, the whole below", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1800 });
    await mockCg(page, TAKEN_IN, {
      families: [KATTA_FAMILY, VALEWEEP_FAMILY],
      family: KATTA_FAMILY,
    });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    // Below the cards: the whole description, in the author's three paragraphs.
    const about = page.getByLabel('About Katta');
    await expect(about).toBeVisible();
    await expect(about.locator('p')).toHaveCount(3);
    await expect(about.locator('p').nth(0)).toContainText('which wall their ancestor held.');
    await expect(about.locator('p').nth(2)).toContainText('A red dragon breaking chains');

    // On the card: the same text, cut to four lines by the page's own rule.
    const cardText = page
      .locator('.cursor-pointer', { hasText: 'Katta' })
      .first()
      .getByText('Commoners often confuse');
    const clamp = await cardText.evaluate((node) => {
      const style = getComputedStyle(node);
      return {
        lines: style.getPropertyValue('-webkit-line-clamp'),
        shown: node.clientHeight,
        full: node.scrollHeight,
        lineHeight: parseFloat(style.lineHeight),
      };
    });
    console.log('card description clamp:', clamp);
    expect(clamp.lines).toBe('4');
    expect(clamp.shown).toBeLessThanOrEqual(Math.ceil(clamp.lineHeight * 4) + 1);
    expect(clamp.full).toBeGreaterThan(clamp.shown);

    await page.waitForTimeout(400);
    await page.screenshot({ path: shot('4-cg-house-description.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
