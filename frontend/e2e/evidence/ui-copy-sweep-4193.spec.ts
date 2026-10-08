import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4193: three real pages on the production bundle, every `/api/**`
 * call answered by fixtures shaped like the serializers, read for what is NOT there any
 * more. The owner's sheet (the abilities band without its "Yours, unless..." note, the
 * physique stack without its colours note), the Friends tab (one line for an empty list)
 * and the Mutes settings page (a heading, no explainer); the sheet at phone width.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4193');
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
const ENTRY = {
  id: ENTRY_ID,
  character: { id: SHEET_ID, name: 'Ilsavet du Verane' },
  profile_picture_url: null,
  tenures: [],
  can_apply: false,
  fullname: 'Ilsavet du Verane',
  quote: '',
  description: '',
  creation_provenance: 'player',
  creation_provenance_display: 'Player-created',
  created_for_table_name: null,
};
const SHEET = {
  id: SHEET_ID,
  can_edit: true,
  identity: {
    name: 'Ilsavet du Verane',
    fullname: 'Ilsavet du Verane',
    concept: "A pawnbroker's daughter who keeps other people's secrets like collateral.",
    quote: '',
    age: 27,
    birthday: null,
    chronological_age: null,
    biological_age: null,
    withered_years: null,
    gender: { id: 1, name: 'Woman' },
    pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
    species: { id: 2, name: 'Human' },
    heritage: null,
    beginnings: [],
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
    height_inches: 70,
    height_band: 'Tall',
    build: null,
    description: '',
    form_traits: [],
  },
  stats: { grit: 3, wit: 4, poise: 2 },
  skills: [],
  path: null,
  distinctions: [],
  magic: null,
  story: { background: '', origin_story_state: 'NOT_STARTED', origin_slots: [] },
  actor_sheet: {
    never_do: '',
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
  viewer_is_friend: true,
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
  ties_ap_this_week: 0,
};

async function mockApi(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const p = new URL(route.request().url()).pathname;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [MINE] });
    if (p === `/api/roster/entries/${ENTRY_ID}/`) return route.fulfill({ json: ENTRY });
    if (p === `/api/character-sheets/${SHEET_ID}/`) return route.fulfill({ json: SHEET });
    if (p === '/api/mutes/' || p === '/api/scenes/friends/')
      return route.fulfill({ json: EMPTY_PAGE });
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (p.startsWith('/api/vitals/'))
      return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    if (p === `/api/roster/kin/tree/${SHEET_ID}/`)
      return route.fulfill({ json: { family: null, nodes: [], parentage: [], unions: [] } });
    if (
      p === '/api/relationships/types/' ||
      p === '/api/relationships/relationships/' ||
      p === '/api/personas/' ||
      p === '/api/journals/entries/' ||
      p === '/api/narrative/my-messages/'
    )
      return route.fulfill({ json: EMPTY_PAGE });
    // Everything else the page asks for on load is a bare list.
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

const GONE = [
  /Yours, unless you open them/,
  /Colours are set in character creation/,
  /Yours and the staff/,
  /Visit another character/,
  /quietly filtered/,
  /They are never told/,
];

test.describe('The copy sweep (#4193) on the production bundle', () => {
  test("the owner's sheet: no note on the abilities band or the physique stack", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await expect(page.getByText('Abilities')).toBeVisible();
    await expect(page.getByTestId('stats-grid')).toBeVisible();
    for (const gone of GONE) await expect(page.getByText(gone)).toHaveCount(0);
    await page.screenshot({ path: shot('01-sheet-owner-1280.png'), fullPage: true });
    await page
      .getByRole('navigation', { name: 'Character sheet sections' })
      .getByRole('button', { name: 'Physical' })
      .click();
    await expect(page.getByText('Physique')).toBeVisible();
    for (const gone of GONE) await expect(page.getByText(gone)).toHaveCount(0);
    await page.screenshot({ path: shot('01b-sheet-physical-1280.png'), fullPage: true });
  });

  test('the Friends tab: one line for an empty list, no explainer', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page);
    await page.goto('/profile/friends');
    await expect(page.getByText('No friends yet.')).toBeVisible();
    for (const gone of GONE) await expect(page.getByText(gone)).toHaveCount(0);
    await page.screenshot({ path: shot('02-friends-empty-1280.png') });
  });

  test('the Mutes settings page: a heading and the list, no explainer', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page);
    await page.goto('/profile/mutes');
    await expect(page.getByRole('heading', { name: 'Muted' })).toBeVisible();
    for (const gone of GONE) await expect(page.getByText(gone)).toHaveCount(0);
    await page.screenshot({ path: shot('03-mutes-1280.png') });
  });

  test('the sheet at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockApi(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await expect(page.getByText('Abilities')).toBeVisible();
    for (const gone of GONE) await expect(page.getByText(gone)).toHaveCount(0);
    await page.screenshot({ path: shot('04-sheet-owner-390.png'), fullPage: true });
  });
});
