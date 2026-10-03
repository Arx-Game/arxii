import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4106: the real `/characters/:entry` sheet on the production
 * bundle, every `/api/**` call answered by fixtures shaped like the serializers.
 *
 * Two readings. The owner's payload carries her goals and the band lists them; a
 * friend's payload (the server gives goals to the owner and staff only) carries none,
 * and the band shows the answers without a goals column. On the Ties tab a membership
 * whose house has exiled the character shows the verdict beside the house.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4106');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const ENTRY_ID = 1;
const SHEET_ID = 20;

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

const MINE = {
  id: ENTRY_ID,
  name: 'Kathryn mar Katta',
  character_id: SHEET_ID,
  profile_picture_url: null,
  primary_persona_id: 9,
  active_persona_id: 9,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

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

const HOUSE_GOAL = {
  domain: 'Ambition',
  horizon: 'long_term',
  ordinal: 1,
  points: 5,
  notes: 'Prove worthy of my house',
};
const FAMILY_GOAL = {
  domain: 'Family',
  horizon: 'short_term',
  ordinal: 1,
  points: 5,
  notes: 'Find out what happened to my sister',
};

/** A `CharacterSheetPayload`, as the owner (goals) or as a friend (none). */
function sheetPayload(owner: boolean) {
  return {
    id: SHEET_ID,
    can_edit: owner,
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
      family: null,
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
    goals: owner ? [HOUSE_GOAL, FAMILY_GOAL] : [],
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
    standing: {
      memberships: [
        {
          organization_id: 40,
          organization: 'House Katta',
          title: 'Princess',
          favor: 'Exiled',
          favor_note: 'For the attempt on the throne.',
        },
        {
          organization_id: 41,
          organization: 'Shroudwatch Academy',
          title: 'Student',
          favor: '',
          favor_note: '',
        },
      ],
      reputations: [],
    },
    covenants: [],
    ties: [],
    ties_ap_this_week: owner ? 0 : null,
  };
}

async function mockSheet(page: Page, owner: boolean) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') return route.fulfill({ json: accountPayload() });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: owner ? [MINE] : [] });
    if (p === `/api/roster/entries/${ENTRY_ID}/`) return route.fulfill({ json: ENTRY });
    if (p === `/api/character-sheets/${SHEET_ID}/`)
      return route.fulfill({ json: sheetPayload(owner) });
    if (p === `/api/roster/kin/tree/${SHEET_ID}/`) {
      return route.fulfill({ json: { family: null, nodes: [], parentage: [], unions: [] } });
    }
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

// --- the readings -------------------------------------------------------------------

test.describe('Goals and a membership standing (#4106) on the production bundle', () => {
  test('the sheet: the owner reads her goals', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, true);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Prove worthy of my house')).toBeVisible();
    await expect(page.getByText('Find out what happened to my sister')).toBeVisible();
    await page.screenshot({ path: shot('sheet-owner-goals-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('the sheet: a friend gets the answers and no goals', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, false);
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Strike first at a table.')).toBeVisible();
    await expect(page.getByText('Prove worthy of my house')).toHaveCount(0);
    await expect(page.getByText('Find out what happened to my sister')).toHaveCount(0);
    await expect(page.getByText('Wants, soon')).toHaveCount(0);
    await page.screenshot({ path: shot('sheet-friend-goals-1280.png'), fullPage: true });
  });

  test("the Ties tab: the house's verdict stands beside the house", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, false);
    await page.goto(`/characters/${ENTRY_ID}`);
    await page
      .getByRole('navigation', { name: 'Character sheet sections' })
      .getByRole('button', { name: 'Ties' })
      .click();
    const katta = page.locator('.refsheet-entry', { hasText: 'House Katta' });
    await expect(katta.getByText('Exiled')).toBeVisible();
    await expect(katta.getByText('Exiled')).toHaveAttribute(
      'title',
      'For the attempt on the throne.'
    );
    // In favour is the default and is not marked.
    const academy = page.locator('.refsheet-entry', { hasText: 'Shroudwatch Academy' });
    await expect(academy.locator('.refsheet-tag')).toHaveCount(0);
    await page.screenshot({ path: shot('sheet-ties-standing-1280.png'), fullPage: true });
  });

  test('at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockSheet(page, false);
    await page.goto(`/characters/${ENTRY_ID}`);
    await page
      .getByRole('navigation', { name: 'Character sheet sections' })
      .getByRole('button', { name: 'Ties' })
      .click();
    await expect(
      page.locator('.refsheet-entry', { hasText: 'House Katta' }).getByText('Exiled')
    ).toBeVisible();
    await page.screenshot({ path: shot('sheet-ties-standing-390.png'), fullPage: true });
  });
});
