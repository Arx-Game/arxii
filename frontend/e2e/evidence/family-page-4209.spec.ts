import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4209: the real `/families/:id` page on the production bundle,
 * every `/api/**` call answered by fixtures shaped like the serializers.
 *
 * The four readings of the approved demo. House Katta as a stranger reads it: the
 * gate, the description, the roll in full-formal names with the played daughter
 * linked, the tree in short names, the selected entry with no relatedness line, the
 * open seats. Tallow, a commoner family with no house: a plain head, a taken-in
 * mother who reads "Hesper ne Marrow Tallow" on the roll and "Hesper ne Marrow" in
 * the tree. Tallow for a viewer who knows the secret: one more person, drawn dashed,
 * selected with "Related as aunt/uncle.". House Katta at phone width.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4209');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const KATTA_ID = 7;
const TALLOW_ID = 8;
const VIEWER_SHEET_ID = 77;
const KATHRYN_SHEET_ID = 20;
const KATHRYN_ENTRY_ID = 2;
const ISMAY_SHEET_ID = 30;
const ISMAY_ENTRY_ID = 3;

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
    selected_entry_id: 9,
    selected_entry: {
      id: 9,
      name: 'Viewer',
      character_id: VIEWER_SHEET_ID,
      roster_type: 'active',
      primary_persona_id: null,
      active_persona_id: null,
      unread_narrative_count: 0,
      unread_pose_count: 0,
    },
  };
}

// --- the trees ----------------------------------------------------------------------

function nodeBase(id: number, family_id: number) {
  return {
    id,
    family_id,
    tier: 'standing',
    is_deceased: false,
    is_appable: false,
    sheet_id: null as number | null,
    roster_entry_id: null as number | null,
    gender: '',
    age: null,
    description: '',
  };
}

/** House Katta: the imperial house, a stranger's reading. */
function katta() {
  return {
    family: {
      id: KATTA_ID,
      name: 'Katta',
      kind: { id: 1, name: 'Noble', styles_as_house: true },
      influence: 0,
      description:
        'The imperial house of Umbros. The throne has not left the name in living memory, ' +
        'and the name has not forgiven anyone who tried. PLACEHOLDER\n\n' +
        'Every Katta learns the court before letters. PLACEHOLDER',
      is_playable: true,
      origin_realm: null,
      born_particle: 'mar',
      taken_in_particle: 'mal',
      standing: null,
      inherited: { aspects: [], features: [], liege_name: '' },
    },
    house: {
      id: 3,
      name: 'House Katta',
      description: '',
      words: 'What the dark keeps, the Katta keep. PLACEHOLDER',
      colors: 'black and silver. PLACEHOLDER',
      sigil_description: 'a crowned key. PLACEHOLDER',
      org_type_name: 'noble_family',
      society_name: 'The Umbral Court',
      family_id: KATTA_ID,
    },
    realm_name: 'Umbros',
    nodes: [
      {
        ...nodeBase(101, KATTA_ID),
        name: 'Alarysa',
        full_name: 'Alarysa mar Katta',
        short_name: 'Alarysa',
        gender: 'Woman',
      },
      {
        ...nodeBase(102, KATTA_ID),
        name: 'Galleron',
        full_name: 'Emperor Galleron ne Valeweep mal Katta',
        short_name: 'Galleron ne Valeweep',
        gender: 'Man',
      },
      {
        ...nodeBase(103, KATTA_ID),
        name: 'Alyssa',
        full_name: 'Princess Alyssa mar Katta',
        short_name: 'Alyssa',
        is_deceased: true,
        gender: 'Woman',
      },
      {
        ...nodeBase(104, KATTA_ID),
        name: 'Kathryn',
        tier: 'pc',
        full_name: 'Princess Kathryn mar Katta',
        short_name: 'Kathryn',
        sheet_id: KATHRYN_SHEET_ID,
        roster_entry_id: KATHRYN_ENTRY_ID,
        gender: 'Woman',
        age: 24,
        description:
          "The younger daughter. Aly's sister, Rysa's second, Leron's favourite; none of " +
          'which she would say aloud. PLACEHOLDER',
      },
    ],
    parentage: [
      { child_id: 103, parent_id: 101, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 103, parent_id: 102, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 104, parent_id: 101, kind: 'biological', is_true: true, via_secret: false },
      { child_id: 104, parent_id: 102, kind: 'biological', is_true: true, via_secret: false },
    ],
    unions: [{ id: 1, kind: 'Marriage', member_ids: [101, 102], ended: false }],
  };
}

/** Tallow, a commoner family with no house; `knows` adds the secret uncle. */
function tallow(knows: boolean) {
  const nodes = [
    {
      ...nodeBase(201, TALLOW_ID),
      name: 'Aldous',
      full_name: 'Aldous Tallow',
      short_name: 'Aldous',
      is_deceased: true,
    },
    {
      ...nodeBase(202, TALLOW_ID),
      name: 'Hesper',
      full_name: 'Hesper ne Marrow Tallow',
      short_name: 'Hesper ne Marrow',
    },
    {
      ...nodeBase(203, TALLOW_ID),
      name: 'Ismay',
      tier: 'pc',
      full_name: 'Ismay Tallow',
      short_name: 'Ismay',
      sheet_id: ISMAY_SHEET_ID,
      roster_entry_id: ISMAY_ENTRY_ID,
    },
    { ...nodeBase(204, TALLOW_ID), name: 'Tam', full_name: 'Tam Tallow', short_name: 'Tam' },
  ];
  const parentage = [
    { child_id: 203, parent_id: 201, kind: 'biological', is_true: true, via_secret: false },
    { child_id: 203, parent_id: 202, kind: 'biological', is_true: true, via_secret: false },
    { child_id: 204, parent_id: 201, kind: 'biological', is_true: true, via_secret: false },
    { child_id: 204, parent_id: 202, kind: 'biological', is_true: true, via_secret: false },
  ];
  if (knows) {
    nodes.push({
      ...nodeBase(205, 9),
      name: 'Bram',
      full_name: 'Bram Ashcombe',
      short_name: 'Bram Ashcombe',
      description: 'Keeps a boat and his counsel. PLACEHOLDER',
    });
    parentage.push({
      child_id: 204,
      parent_id: 205,
      kind: 'biological',
      is_true: true,
      via_secret: true,
    });
  }
  return {
    family: {
      id: TALLOW_ID,
      name: 'Tallow',
      kind: { id: 2, name: 'Commoner', styles_as_house: false },
      influence: 0,
      description:
        'Chandlers on the lower quay for four generations; the shop smells of mutton fat ' +
        'and the family of nothing else. PLACEHOLDER',
      is_playable: true,
      origin_realm: 4,
      born_particle: '',
      taken_in_particle: '',
      standing: null,
      inherited: { aspects: [], features: [], liege_name: '' },
    },
    house: null,
    realm_name: 'Arx',
    nodes,
    parentage,
    unions: [{ id: 2, kind: 'Marriage', member_ids: [201, 202], ended: false }],
  };
}

function kattaSeats() {
  return {
    slots: [
      {
        id: 1,
        name: 'A cousin of the Katta line',
        name_locked: false,
        description: "Of Alarysa's generation; raised at court. PLACEHOLDER",
        age_min: null,
        age_max: null,
        allowed_genders: [],
        family: KATTA_ID,
      },
    ],
    pools: [
      {
        id: 1,
        family: KATTA_ID,
        description: 'Wards of the Katta PLACEHOLDER',
        count_remaining: 2,
        age_min: null,
        age_max: null,
        allowed_genders: [],
        parent_names: ['Alarysa', 'Galleron'],
      },
    ],
  };
}

function tallowSeats() {
  return {
    slots: [],
    pools: [
      {
        id: 2,
        family: TALLOW_ID,
        description: '',
        count_remaining: 1,
        age_min: null,
        age_max: null,
        allowed_genders: [],
        parent_names: ['Aldous', 'Hesper'],
      },
    ],
  };
}

interface Fixture {
  knows: boolean;
  label: string | null;
}

async function mockApi(page: Page, { knows, label }: Fixture) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') return route.fulfill({ json: accountPayload() });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [] });
    if (p === `/api/roster/families/${KATTA_ID}/tree/`) return route.fulfill({ json: katta() });
    if (p === `/api/roster/families/${KATTA_ID}/slots/`) {
      return route.fulfill({ json: kattaSeats() });
    }
    if (p === `/api/roster/families/${TALLOW_ID}/tree/`) {
      return route.fulfill({ json: tallow(knows) });
    }
    if (p === `/api/roster/families/${TALLOW_ID}/slots/`) {
      return route.fulfill({ json: tallowSeats() });
    }
    if (p === '/api/roster/kin/relationship/') return route.fulfill({ json: { label } });
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (p === '/api/personas/' || p === '/api/narrative/my-messages/') {
      return route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    }
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

// --- the readings -------------------------------------------------------------------

test.describe('The family page (#4209) on the production bundle', () => {
  test('House Katta, as a stranger reads it', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page, { knows: false, label: null });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/families/${KATTA_ID}`);

    await expect(page.getByRole('heading', { level: 1, name: 'House Katta' })).toBeVisible();
    await expect(page.getByText('Noble House · Umbros')).toBeVisible();
    await expect(page.getByText(/What the dark keeps, the Katta keep/)).toBeVisible();
    await expect(page.getByText(/Colours: black and silver/)).toBeVisible();
    await expect(page.getByText(/The imperial house of Umbros/)).toBeVisible();

    const roll = page.getByRole('region', { name: 'The roll' });
    await expect(roll.getByText('Emperor Galleron ne Valeweep mal Katta')).toBeVisible();
    await expect(roll.getByText('Princess Alyssa mar Katta †')).toBeVisible();
    await expect(roll.getByRole('link', { name: 'Princess Kathryn mar Katta' })).toHaveAttribute(
      'href',
      `/characters/${KATHRYN_ENTRY_ID}`
    );
    const tree = page.getByRole('region', { name: 'The tree' });
    await expect(tree.getByText('Galleron ne Valeweep')).toBeVisible();
    await expect(tree.getByText('Alyssa †')).toBeVisible();
    await expect(tree.getByRole('link', { name: 'Kathryn' })).toHaveAttribute(
      'href',
      `/characters/${KATHRYN_ENTRY_ID}`
    );
    await expect(page.locator('article.family-page')).not.toContainText(/standing|name only/);

    const seats = page.getByRole('region', { name: 'Open seats' });
    await expect(seats.getByText('A cousin of the Katta line')).toBeVisible();
    await expect(seats.getByText('open', { exact: true })).toBeVisible();
    await expect(seats.getByText('2 seats')).toBeVisible();
    await page.screenshot({ path: shot('01-house-katta-1280.png'), fullPage: true });

    await page.locator('[data-node-id="104"] rect').click({ position: { x: 8, y: 8 } });
    const selected = page.getByRole('region', { name: 'Selected' });
    await expect(selected.getByRole('link', { name: 'Princess Kathryn mar Katta' })).toBeVisible();
    await expect(selected.getByText(/The younger daughter/)).toBeVisible();
    await expect(selected).not.toContainText(/Related as|determinable|Nobody on the roster/);
    await page.screenshot({ path: shot('02-house-katta-selected-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('Tallow, a commoner family with no house, as a stranger reads it', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page, { knows: false, label: 'cousin' });
    await page.goto(`/families/${TALLOW_ID}`);

    await expect(page.getByRole('heading', { level: 1, name: 'Tallow' })).toBeVisible();
    await expect(page.getByText('Commoner Family · Arx')).toBeVisible();
    await expect(page.getByText(/House Tallow/)).toHaveCount(0);
    await expect(page.getByText(/Colours:/)).toHaveCount(0);
    const roll = page.getByRole('region', { name: 'The roll' });
    await expect(roll.getByText('Hesper ne Marrow Tallow')).toBeVisible();
    await expect(roll.getByText('Aldous Tallow †')).toBeVisible();
    await expect(roll.getByRole('link', { name: 'Ismay Tallow' })).toHaveAttribute(
      'href',
      `/characters/${ISMAY_ENTRY_ID}`
    );
    const tree = page.getByRole('region', { name: 'The tree' });
    await expect(tree.getByText('Hesper ne Marrow')).toBeVisible();
    await expect(tree.getByText('Bram Ashcombe')).toHaveCount(0);
    await expect(page.locator('[data-via-secret="true"]')).toHaveCount(0);

    await page.locator('[data-node-id="203"] rect').click({ position: { x: 8, y: 8 } });
    await expect(page.getByText('Related as cousin.')).toBeVisible();
    await expect(page.getByText('1 seat')).toBeVisible();
    await page.screenshot({ path: shot('03-tallow-1280.png'), fullPage: true });
  });

  test('Tallow, for a viewer who knows the secret', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page, { knows: true, label: 'aunt/uncle' });
    await page.goto(`/families/${TALLOW_ID}`);

    const roll = page.getByRole('region', { name: 'The roll' });
    await expect(roll.getByText('Bram Ashcombe')).toBeVisible();
    await expect(page.locator('[data-via-secret="true"]')).toHaveCount(1);
    const tree = page.getByRole('region', { name: 'The tree' });
    await expect(tree.getByText('Bram Ashcombe')).toBeVisible();

    await page.locator('[data-node-id="205"] rect').click({ position: { x: 8, y: 8 } });
    const selected = page.getByRole('region', { name: 'Selected' });
    await expect(selected.getByText('Bram Ashcombe')).toBeVisible();
    await expect(selected.getByText(/Keeps a boat/)).toBeVisible();
    // An unplayed person: no sheet to relate to, so no line, whatever the endpoint says.
    await expect(selected).not.toContainText(/Related as/);
    await page.screenshot({ path: shot('04-tallow-knows-1280.png'), fullPage: true });
  });

  test('House Katta at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockApi(page, { knows: false, label: null });
    await page.goto(`/families/${KATTA_ID}`);
    await expect(page.getByRole('heading', { level: 1, name: 'House Katta' })).toBeVisible();
    await page.locator('[data-node-id="104"] rect').click({ position: { x: 8, y: 8 } });
    await expect(
      page.getByRole('region', { name: 'Selected' }).getByRole('link', {
        name: 'Princess Kathryn mar Katta',
      })
    ).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await page.screenshot({ path: shot('05-house-katta-390.png'), fullPage: true });
  });
});
