import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4226 (staff edit mode, piece D): the real `/characters/:entry`
 * sheet on the production bundle, signed in as staff, every `/api/**` call answered by
 * fixtures shaped like the serializers. Staff turn edit mode on with the header's own
 * toggle, then fill a bare sheet's family tree, residence and reputation in the rows
 * band; each save answers with the refreshed sheet, which the band redraws.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4226');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const ENTRY_ID = 1;
const SHEET_ID = 20;

const ACCOUNT = {
  id: 1,
  username: 'staff-e2e',
  display_name: 'Staff E2E',
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

const ENTRY = {
  id: ENTRY_ID,
  character: { id: SHEET_ID, name: 'Kathryn mar Katta', galleries: [] },
  profile_picture: null,
  tenures: [],
  can_apply: false,
  fullname: 'Kathryn mar Katta',
  quote: '',
  description: '',
  creation_provenance: 'staff',
  creation_provenance_display: 'Staff-created',
  created_for_table_name: null,
};

interface EstateRows {
  kin_node: { id: number; name: string } | null;
  residences: { id: number; name: string }[];
  properties: { id: number; name: string }[];
  reputations: { organization: number; name: string; value: number }[];
}

const BARE: EstateRows = { kin_node: null, residences: [], properties: [], reputations: [] };

function stored(estate: EstateRows) {
  return {
    rows: {
      stats: {},
      skills: {},
      specializations: {},
      distinctions: [],
      form: {},
      markings: [],
      beginnings: null,
      path: null,
      class_level: null,
      public_being: null,
      secret_being: null,
      has_vitals: true,
      has_gift: true,
      has_aura: false,
      ...estate,
    },
    prose: {
      description: '',
      background: '',
      concept: '',
      real_concept: '',
      quote: '',
      never_do: '',
      protect: '',
      fear: '',
      obituary: '',
      glimpse: '',
    },
    name: 'Kathryn mar Katta',
    ic_birth_year: null,
    true_height_inches: null,
    weight_pounds: null,
    marital_status: 'single',
    vocation: '',
    social_rank: 10,
    build: null,
    gender: null,
    pronouns: null,
    species: null,
    heritage: null,
    origin_realm: null,
    family: null,
    tarot_card: null,
    tarot_reversed: false,
  };
}

function sheetPayload(estate: EstateRows) {
  return {
    id: SHEET_ID,
    can_edit: true,
    staff_edit: stored(estate),
    identity: {
      name: 'Kathryn mar Katta',
      fullname: 'Kathryn mar Katta',
      concept: '',
      quote: '',
      age: 24,
      birthday: null,
      chronological_age: null,
      biological_age: null,
      withered_years: null,
      gender: null,
      pronouns: { subject: 'she', object: 'her', possessive: 'hers' },
      species: null,
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
      height_inches: null,
      height_band: '',
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

const STAFF_OPTIONS = {
  stats: [],
  skills: [],
  specializations: [],
  distinctions: [],
  form_traits: [],
  beginnings: [],
  paths: [],
  beings: [],
  marking_regions: [],
  marking_kinds: [],
  enemy_kinds: [],
  enemy_degrees: [],
  enemy_power_tiers: [],
};

const ROOMS = [
  { id: 70, name: 'Katta Manor, East Wing' },
  { id: 71, name: 'Katta Manor, Solar' },
];

function estateOptions(room: string) {
  return {
    open_positions: [
      { id: 40, name: 'Second daughter (House Katta)' },
      { id: 43, name: 'Ward of the house (House Katta)' },
    ],
    families: [{ id: 41, name: 'House Katta' }],
    rooms: room ? ROOMS.filter((r) => r.name.toLowerCase().includes(room.toLowerCase())) : [],
    grant_profiles: [{ id: 50, name: 'Minor noble townhouse' }],
    house_claims: [],
    vacancies: [{ id: 60, name: 'House Katta: Household guard' }],
    organizations: [
      { id: 42, name: 'The Lamplighters' },
      { id: 44, name: 'Shroudwatch Academy' },
    ],
  };
}

/** The sheet as the server would answer after each staff save. */
async function mockSheet(page: Page) {
  let estate: EstateRows = { ...BARE };
  const writes: { path: string; body: unknown }[] = [];
  await page.route('**/api/**', async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const p = url.pathname;
    const base = `/api/character-sheets/${SHEET_ID}`;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [] });
    if (p === `/api/roster/entries/${ENTRY_ID}/`) return route.fulfill({ json: ENTRY });
    if (p === `${base}/`) return route.fulfill({ json: sheetPayload(estate) });
    if (p === `${base}/staff-options/`) return route.fulfill({ json: STAFF_OPTIONS });
    if (p === `${base}/staff-estate-options/`) {
      return route.fulfill({ json: estateOptions(url.searchParams.get('room') ?? '') });
    }
    if (request.method() !== 'GET' && p.startsWith(`${base}/staff-`)) {
      const body = request.postDataJSON() as Record<string, number | null>;
      writes.push({ path: p.slice(base.length + 1, -1), body });
      if (p === `${base}/staff-kinship/` && body.node === 40) {
        estate = { ...estate, kin_node: { id: 40, name: 'Second daughter (House Katta)' } };
      }
      if (p === `${base}/staff-residence/` && body.room_profile === 70) {
        estate = { ...estate, residences: [ROOMS[0]] };
      }
      if (p === `${base}/staff-reputation/`) {
        estate = {
          ...estate,
          reputations: [{ organization: 42, name: 'The Lamplighters', value: Number(body.value) }],
        };
      }
      return route.fulfill({ json: sheetPayload(estate) });
    }
    if (p === `/api/roster/kin/tree/${SHEET_ID}/`) {
      return route.fulfill({ json: { family: null, nodes: [], parentage: [], unions: [] } });
    }
    if (
      p === '/api/relationships/types/' ||
      p === '/api/relationships/relationships/' ||
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
    if (request.method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
  return writes;
}

test.describe('Staff edit mode, piece D (#4226) on the production bundle', () => {
  test('staff fill a bare sheet: family tree, residence and reputation', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const writes = await mockSheet(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/characters/${ENTRY_ID}`);
    await page.getByRole('switch', { name: 'Edit' }).click();

    const band = page.getByTestId('staff-rows-band');
    const tree = band.getByRole('region', { name: 'Family tree' });
    await expect(tree.getByRole('button', { name: 'Claim position' })).toBeVisible();
    await tree.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('01-bare-sheet-estate-editors-1280.png'), fullPage: true });

    await tree.getByRole('combobox', { name: 'Open position' }).selectOption('40');
    await tree.getByRole('button', { name: 'Claim position' }).click();
    await expect(tree.getByText('Second daughter (House Katta)')).toBeVisible();

    const residence = band.getByRole('region', { name: 'Residence' });
    await residence.getByRole('textbox', { name: 'Find a room' }).fill('east');
    await residence.getByRole('button', { name: 'Find' }).click();
    await residence.getByRole('combobox', { name: 'Room' }).selectOption('70');
    await residence.getByRole('button', { name: 'Make residence' }).click();
    await expect(
      residence.getByRole('listitem').filter({ hasText: 'Katta Manor, East Wing' })
    ).toBeVisible();

    const reputation = band.getByRole('region', { name: 'Reputation' });
    await reputation.getByRole('combobox', { name: 'Organization' }).selectOption('42');
    await reputation.getByRole('spinbutton', { name: 'Reputation' }).fill('250');
    await reputation.getByRole('button', { name: 'Set reputation' }).click();
    await expect(
      reputation.getByRole('spinbutton', { name: 'The Lamplighters reputation' })
    ).toHaveValue('250');

    await tree.scrollIntoViewIfNeeded();
    await page.screenshot({ path: shot('02-filled-estate-rows-1280.png'), fullPage: true });
    expect(writes).toEqual([
      { path: 'staff-kinship', body: { node: 40 } },
      { path: 'staff-residence', body: { room_profile: 70 } },
      { path: 'staff-reputation', body: { organization: 42, value: 250 } },
    ]);
    expect(errors).toEqual([]);
  });

  test('at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockSheet(page);
    await page.goto(`/characters/${ENTRY_ID}`);
    await page.getByRole('switch', { name: 'Edit' }).click();
    const tree = page.getByTestId('staff-rows-band').getByRole('region', { name: 'Family tree' });
    await expect(tree.getByRole('button', { name: 'Claim position' })).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot('03-estate-editors-390.png'), fullPage: true });
  });
});
