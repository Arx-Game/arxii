import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/** Review evidence for #5114, on the production bundle with `/api/**` answered by fixtures. */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '5114');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const HOUSE_ID = 9;
const FAMILY_ID = 4;

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

const person = (id: number, name: string, basis: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  tier: 'standing',
  family_id: FAMILY_ID,
  is_deceased: false,
  is_missing: false,
  obituary: '',
  is_appable: false,
  sheet_id: null,
  roster_entry_id: null,
  full_name: name,
  short_name: name,
  gender: '',
  age: null,
  description: '',
  believed_deceased: false,
  basis,
  ...extra,
});
/** Galleron married in and was entered first: he has the lowest id and comes
 * first in the payload. He holds the throne, so he is `head_id`. */
const FAMILY = {
  family_id: FAMILY_ID,
  head_id: 10,
  nodes: [
    person(10, 'Galleron mal Katta', 'married_in'),
    person(11, 'Alarysa mar Katta', 'born', { is_deceased: true }),
    person(12, 'Alyssa mar Katta', 'born'),
    person(13, 'Kathryn mar Katta', 'born', { is_appable: true }),
  ],
  parentage: [
    { parent_id: 11, child_id: 12, kind: 'birth', is_true: true, via_secret: false },
    { parent_id: 10, child_id: 12, kind: 'birth', is_true: true, via_secret: false },
    { parent_id: 11, child_id: 13, kind: 'birth', is_true: true, via_secret: false },
    { parent_id: 10, child_id: 13, kind: 'birth', is_true: true, via_secret: false },
  ],
  unions: [{ id: 1, kind: 'Marriage', member_ids: [10, 11], via_secret: false }],
};
const HOUSES = {
  count: 3,
  next: null,
  previous: null,
  results: [
    {
      id: HOUSE_ID,
      name: 'Katta',
      house_state: 'standing',
      published_at: null,
      family_id: FAMILY_ID,
    },
    { id: 21, name: 'Valeweep', house_state: 'standing', published_at: null, family_id: 6 },
    { id: 22, name: 'Piropa', house_state: 'standing', published_at: null, family_id: 7 },
  ],
};

const HOUSE_DOCUMENT = {
  house: {
    id: HOUSE_ID,
    name: 'Katta',
    description: '',
    words: '',
    colors: '',
    sigil_description: '',
    house_state: 'standing',
    published_at: null,
    particle: { born: 'mar', taken_in: 'mal' },
    default_succession_law: { name: 'Infernal Enatic - Durance', codex_entry_id: null },
    patron: null,
    facets: [],
    charter_questions: [],
    features: [],
    offices: [],
    observances: [],
  },
  family: FAMILY,
  household: [],
  realm: {
    sworn_to: '',
    obligation_pct: null,
    holds: 'Umbros',
    demesne: [],
    vassals: [],
    realm_id: 1,
    default_tithe_pct: 10,
    realm_theme: '',
  },
  lands: { count: 0, population: 0, produces: [], seat: '', baronies: [] },
  estate: [],
  books: { income_week: 0, uncollected: 0, treasury: 0, streams: 0 },
  forces: [],
  openings: { appable: [], posts: [], vacant_seats: [] },
  turf: null,
};

const EMPTY_PAGE = { count: 0, next: null, previous: null, results: [] };
/** Nav-chrome reads that expect a bare array, not a page. */
const BARE_ARRAYS = [
  '/api/magic/character-resonances/',
  '/api/precapture-consent-requests/',
  '/api/items/makeover-requests/',
  '/api/gm/summon-offers/',
  '/api/ceremonies/seance-offers/',
  '/api/ceremonies/conversion-offers/',
  '/api/magic/rituals/sessions/',
  '/api/personas/',
];

async function mockApi(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [CHARACTER] });
    if (p === `/api/almanach/houses/${HOUSE_ID}/document/`) {
      return route.fulfill({ json: HOUSE_DOCUMENT });
    }
    if (p === '/api/almanach/houses/') return route.fulfill({ json: HOUSES });
    if (p === '/api/character-creation/genders/') return route.fulfill({ json: [] });
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (BARE_ARRAYS.includes(p)) return route.fulfill({ json: [] });
    if (route.request().method() === 'GET') return route.fulfill({ json: EMPTY_PAGE });
    return route.fulfill({ json: { message: 'Done.', success: true, data: null } });
  });
}

test('#5114: the tree seats the couple by birth, names the head by the title, and the add dialog leaves out the house itself', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockApi(page);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`/staff/almanach/houses/${HOUSE_ID}`);
  await page.getByRole('button', { name: 'The Family', exact: true }).click();
  await expect(page.locator('main.chapter h3').first()).toContainText('Family');

  const rows = page.locator('main.chapter .who:has(.nm)');
  const read = await rows.evaluateAll((nodes) =>
    nodes.map((node) => ({
      name: node.querySelector('.nm')?.textContent?.trim(),
      rel: node.querySelector('.rel')?.textContent?.trim(),
    }))
  );
  console.log('tree rows:', JSON.stringify(read));
  expect(read).toEqual([
    { name: 'Alarysa mar Katta', rel: '' },
    { name: 'Galleron mal Katta', rel: 'consort · head of house' },
    { name: 'Alyssa mar Katta', rel: 'child' },
    { name: 'Kathryn mar Katta', rel: 'child' },
  ]);
  await page.screenshot({ path: shot('1-family-tree.png'), fullPage: true });

  await page.getByRole('button', { name: 'Add family member' }).click();
  await page.locator('#add-kin-born-into').click();
  const options = page.getByRole('option');
  await expect(options).toHaveText(['Valeweep', 'Piropa']);
  await page.screenshot({ path: shot('2-born-into.png'), fullPage: false });
  expect(errors, errors.join('\n')).toEqual([]);
});
