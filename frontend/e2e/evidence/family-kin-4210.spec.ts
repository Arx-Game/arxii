import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4210: the real `/characters/:entry` sheet on the production
 * bundle, every `/api/**` call answered by fixtures shaped like the serializers.
 *
 * Four readings. The House row on the sheet's front is plain text, not a link into the
 * org route. On the Ties tab the Kin block reads the family as "House Katta" with the
 * family's own description under it; a selected sheeted kinsperson links to their sheet
 * by roster entry id (a third id space beside the Kinsperson pk and the sheet pk), and
 * an unplayed NPC links nowhere. A commoner family is read by its bare name.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4210');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const ENTRY_ID = 1;
const SHEET_ID = 20;
const SISTER_ENTRY_ID = 2;
const SISTER_SHEET_ID = 21;
const FAMILY_ID = 7;

function accountPayload() {
  return {
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
}

// --- the sheet ----------------------------------------------------------------------

const ENTRY = {
  id: ENTRY_ID,
  character: { id: SHEET_ID, name: 'Kathryn mar Katta', galleries: [] },
  profile_picture: null,
  tenures: [],
  can_apply: false,
  fullname: 'Kathryn mar Katta',
  quote: '',
  description: '',
  creation_provenance: 'player',
  creation_provenance_display: 'Player-created',
  created_for_table_name: null,
};

/** A `CharacterSheetPayload` as a friend reads it; the family is the row under test. */
function sheetPayload() {
  return {
    id: SHEET_ID,
    can_edit: false,
    identity: {
      name: 'Kathryn mar Katta',
      fullname: 'Kathryn mar Katta',
      concept: 'PLACEHOLDER concept line.',
      quote: '',
      age: 24,
      birthday: null,
      chronological_age: null,
      biological_age: null,
      withered_years: null,
      gender: { id: 1, name: 'Woman' },
      pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
      species: { id: 2, name: 'Human' },
      heritage: null,
      beginnings: [{ id: 5, name: 'Nobility' }],
      family: { id: FAMILY_ID, name: 'Katta' },
      tarot_card: null,
      origin: null,
      path: null,
      worship: null,
      worship_sincere: null,
      current_mood: null,
      vacancy: null,
    },
    appearance: {
      height_inches: null,
      height_band: 'Tall',
      build: null,
      description: '',
      form_traits: [],
    },
    stats: {},
    skills: [],
    path: null,
    distinctions: [],
    magic: null,
    story: { background: '', origin_story_state: 'NOT_STARTED', origin_slots: [] },
    actor_sheet: {
      never_do: 'Strike first at a table.',
      protect: '',
      fear: '',
      enemy_public_line: '',
      enemy: null,
      introductions: [],
    },
    goals: [],
    beats: [],
    personas: [],
    theming: {},
    profile_picture: null,
    current_residence: null,
    looks: [],
    plate_ink: 'ember',
    worn: [],
    mentors: [],
    domains: [],
    keyring: [],
    standing: { memberships: [], reputations: [] },
    covenants: [],
    ties: [],
    ties_ap_this_week: null,
  };
}

// --- the kin tree -------------------------------------------------------------------

/** The `kin/tree/<character_id>/` payload: the family and four kin. Kathryn and her
 * sister are played (a sheet and a roster entry each); the parents are NPCs with
 * neither, so they have nowhere to link. */
function kinTree(houseStyled: boolean) {
  return {
    family: {
      id: FAMILY_ID,
      name: 'Katta',
      kind: houseStyled
        ? { id: 1, name: 'Noble', styles_as_house: true }
        : { id: 2, name: 'Commoner', styles_as_house: false },
      influence: 0,
      description:
        'Old blood of the eastern marches. The Katta hold the salt road and the ferry ' +
        'tolls, and have buried three kings. PLACEHOLDER.',
      is_playable: true,
      origin_realm: null,
      born_particle: houseStyled ? 'mar' : '',
      taken_in_particle: houseStyled ? 'mar' : '',
      standing: null,
      inherited: { aspects: [], features: [], liege_name: '' },
    },
    nodes: [
      {
        id: 101,
        name: 'Kathryn mar Katta',
        tier: 'pc',
        family_id: FAMILY_ID,
        is_deceased: false,
        is_appable: false,
        sheet_id: SHEET_ID,
        roster_entry_id: ENTRY_ID,
        gender: 'Woman',
        age: 24,
        description: '',
      },
      {
        id: 102,
        name: 'Maren mar Katta',
        tier: 'pc',
        family_id: FAMILY_ID,
        is_deceased: false,
        is_appable: false,
        sheet_id: SISTER_SHEET_ID,
        roster_entry_id: SISTER_ENTRY_ID,
        gender: 'Woman',
        age: 27,
        description: 'The elder sister, who stayed. PLACEHOLDER.',
      },
      {
        id: 103,
        name: 'Aldous mar Katta',
        tier: 'described',
        family_id: FAMILY_ID,
        is_deceased: true,
        is_appable: false,
        sheet_id: null,
        roster_entry_id: null,
        gender: 'Man',
        age: null,
        description: 'Their father, lost at the ferry crossing. PLACEHOLDER.',
      },
      {
        id: 104,
        name: 'Ismay mar Katta',
        tier: 'name_only',
        family_id: FAMILY_ID,
        is_deceased: false,
        is_appable: false,
        sheet_id: null,
        roster_entry_id: null,
        gender: 'Woman',
        age: null,
        description: '',
      },
    ],
    parentage: [
      { child_id: 101, parent_id: 103, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 101, parent_id: 104, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 102, parent_id: 103, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 102, parent_id: 104, kind: 'biological', is_true: true, via_secret: false },
    ],
    unions: [],
  };
}

async function mockSheet(page: Page, { houseStyled }: { houseStyled: boolean }) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') return route.fulfill({ json: accountPayload() });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [] });
    if (p === `/api/roster/entries/${ENTRY_ID}/`) return route.fulfill({ json: ENTRY });
    if (p === `/api/character-sheets/${SHEET_ID}/`) return route.fulfill({ json: sheetPayload() });
    if (p === `/api/roster/kin/tree/${SHEET_ID}/`) {
      return route.fulfill({ json: kinTree(houseStyled) });
    }
    if (p === '/api/roster/kin/relationship/') return route.fulfill({ json: { label: 'sibling' } });
    if (p === '/api/relationships/types/' || p === '/api/relationships/relationships/') {
      return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    }
    if (
      p === '/api/personas/' ||
      p === '/api/journals/entries/' ||
      p === '/api/narrative/my-messages/'
    ) {
      return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    }
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (p.startsWith('/api/vitals/')) {
      return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

async function openTies(page: Page) {
  await page
    .getByRole('navigation', { name: 'Character sheet sections' })
    .getByRole('button', { name: 'Ties' })
    .click();
}

// --- the readings -------------------------------------------------------------------

test.describe('The family on the sheet (#4210) on the production bundle', () => {
  test('the sheet front: the House row names the family without a link', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, { houseStyled: true });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Strike first at a table.')).toBeVisible();
    await expect(page.getByText('Katta', { exact: true })).toBeVisible();
    await expect(page.locator('a[href^="/orgs/"]')).toHaveCount(0);
    await page.screenshot({ path: shot('01-sheet-front-house-row-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('the Kin block: House Katta, its description, and a sister who links to her sheet', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, { houseStyled: true });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await openTies(page);
    await expect(page.getByText('House Katta')).toBeVisible();
    await expect(page.getByText(/Old blood of the eastern marches/)).toBeVisible();
    await page.screenshot({
      path: shot('02-kin-block-house-description-1280.png'),
      fullPage: true,
    });

    await page.locator('[data-node-id="102"]').click();
    const sister = page.getByRole('link', { name: 'Maren mar Katta' });
    await expect(sister).toBeVisible();
    await expect(sister).toHaveAttribute('href', `/characters/${SISTER_ENTRY_ID}`);
    await expect(page.getByText('Related as sibling.')).toBeVisible();
    await page.screenshot({ path: shot('03-kin-selected-sister-link-1280.png'), fullPage: true });

    await page.locator('[data-node-id="103"]').click();
    await expect(page.getByRole('link', { name: 'Aldous mar Katta' })).toHaveCount(0);
    await expect(page.getByText(/Nobody on the roster answers to this person/)).toBeVisible();
    await page.screenshot({ path: shot('04-kin-selected-npc-no-link-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('a commoner family is read by its bare name', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, { houseStyled: false });
    await page.goto(`/characters/${ENTRY_ID}`);
    await openTies(page);
    await expect(page.locator('.refsheet-ledger', { hasText: /^Katta$/ })).toBeVisible();
    await expect(page.getByText('House Katta')).toHaveCount(0);
    await page.screenshot({ path: shot('05-kin-block-commoner-1280.png'), fullPage: true });
  });

  test('at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockSheet(page, { houseStyled: true });
    await page.goto(`/characters/${ENTRY_ID}`);
    await openTies(page);
    await expect(page.getByText('House Katta')).toBeVisible();
    await page.locator('[data-node-id="102"]').click();
    await expect(page.getByRole('link', { name: 'Maren mar Katta' })).toHaveAttribute(
      'href',
      `/characters/${SISTER_ENTRY_ID}`
    );
    await page.screenshot({ path: shot('06-kin-block-390.png'), fullPage: true });
  });
});
