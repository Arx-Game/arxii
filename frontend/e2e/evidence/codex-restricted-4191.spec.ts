import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4191: the real `/codex` page on the production bundle, every
 * `/api/**` call answered by fixtures shaped like the serializers.
 *
 * Readings: staff at a subject (no banner, restricted entries toned, no badges), a
 * one-character player at the same subject (toned, no badge bearing their own name), a
 * two-character player (the badges and the scope dropdown), a restricted entry's
 * detail, the search results, phone width. Every name and line is placeholder copy;
 * the assertion that matters is that the tone rule reaches the page (#3667).
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4191');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

type Viewer = 'staff' | 'player' | 'two';
const SUBJECT_ID = 3;

const PATH = [
  { type: 'category', id: 1, name: 'The World' },
  { type: 'subject', id: SUBJECT_ID, name: 'Geography' },
];
const TREE = [
  {
    id: 1,
    name: 'The World',
    description: 'The lands, the roads between them, and what lies past the last of them.',
    subjects: [{ id: SUBJECT_ID, name: 'Geography', has_children: false, entry_count: 4 }],
  },
];
const SUBJECT = {
  id: SUBJECT_ID,
  name: 'Geography',
  description: 'Where the realms lie.',
  display_order: 0,
  category: 1,
  category_name: 'The World',
  parent: null,
  parent_name: null,
  path: PATH,
};

const CHARACTERS = [
  { id: 1, name: 'Ilsavet du Verane', character_id: 20 },
  { id: 2, name: 'Corwen Hale', character_id: 21 },
];
const CHARACTER_COUNT: Record<Viewer, number> = { staff: 0, player: 1, two: 2 };
function mine(viewer: Viewer) {
  return CHARACTERS.slice(0, CHARACTER_COUNT[viewer]).map((c) => ({
    ...c,
    profile_picture_url: null,
    primary_persona_id: c.id,
    active_persona_id: c.id,
    unread_narrative_count: 0,
    lifecycle_state: 'ALIVE',
    roster_type: 'Active',
    character_type: 'PC',
  }));
}

interface Seed {
  id: number;
  name: string;
  summary: string;
  is_public: boolean;
  /** Which of the viewer's characters hold it, and how, when the viewer is a player. */
  held?: 'known' | 'uncovered';
}
const SEEDS: Seed[] = [
  {
    id: 1,
    name: 'The Shroud',
    summary: 'A grey veil no army and no messenger ever crossed.',
    is_public: true,
  },
  {
    id: 2,
    name: 'The Lower Stair',
    summary: 'The old city, the harbour, the steps between.',
    is_public: true,
  },
  {
    id: 3,
    name: 'The Pale Road',
    summary: 'A road the maps leave out.',
    is_public: false,
    held: 'known',
  },
  {
    id: 4,
    name: 'Where the Shroud Thins',
    summary: 'Three places. Two of them are lies.',
    is_public: false,
    held: 'uncovered',
  },
];

function knowers(seed: Seed, viewer: Viewer) {
  if (viewer === 'staff' || !seed.held) return [];
  return mine(viewer).map((c) => ({
    roster_entry_id: c.id,
    character_name: c.name,
    status: seed.held,
    research_progress: seed.held === 'uncovered' ? 4 : 10,
  }));
}
function listItem(seed: Seed, viewer: Viewer) {
  const known_by = knowers(seed, viewer);
  return {
    id: seed.id,
    name: seed.name,
    summary: seed.summary,
    is_public: seed.is_public,
    is_featured: false,
    featured_order: null,
    subject: SUBJECT_ID,
    subject_name: 'Geography',
    subject_path: PATH,
    display_order: seed.id,
    knowledge_status: known_by[0]?.status ?? null,
    known_by,
    art_url: null,
    perspective_of: null,
    also_filed_under: [],
  };
}
function detail(seed: Seed, viewer: Viewer) {
  const item = listItem(seed, viewer);
  const readable = viewer === 'staff' || seed.is_public || item.knowledge_status === 'known';
  return {
    ...item,
    quote: '',
    lore_content: readable ? `${seed.summary} The road runs north of the last milestone.` : null,
    mechanics_content: null,
    lore_links: [],
    mechanics_links: [],
    learn_threshold: 10,
    research_progress: item.knowledge_status === 'uncovered' ? 4 : null,
  };
}
/** The API returns what the viewer may see: public, plus held, plus everything for staff. */
function visible(viewer: Viewer) {
  return SEEDS.filter((s) => viewer === 'staff' || s.is_public || s.held);
}

function accountPayload(viewer: Viewer) {
  return {
    id: 1,
    username: 'walk-e2e',
    display_name: 'Walk E2E',
    email: '',
    email_verified: true,
    last_login: null,
    can_create_characters: true,
    is_staff: viewer === 'staff',
    is_gm: false,
    available_characters: [],
    pending_applications: [],
    selected_entry_id: null,
    selected_entry: null,
  };
}

async function mockCodex(page: Page, viewer: Viewer) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') return route.fulfill({ json: accountPayload(viewer) });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: mine(viewer) });
    if (p === '/api/codex/categories/tree/') return route.fulfill({ json: TREE });
    if (p === `/api/codex/subjects/${SUBJECT_ID}/`) return route.fulfill({ json: SUBJECT });
    if (p === `/api/codex/subjects/${SUBJECT_ID}/children/`) return route.fulfill({ json: [] });
    if (p === '/api/codex/entries/') {
      if (url.searchParams.get('featured')) return route.fulfill({ json: [] });
      const search = url.searchParams.get('search')?.toLowerCase();
      const seeds = visible(viewer).filter((s) => !search || s.name.toLowerCase().includes(search));
      return route.fulfill({ json: seeds.map((s) => listItem(s, viewer)) });
    }
    const entry = p.match(/^\/api\/codex\/entries\/(\d+)\/$/);
    if (entry) {
      const seed = visible(viewer).find((s) => s.id === Number(entry[1]));
      return seed
        ? route.fulfill({ json: detail(seed, viewer) })
        : route.fulfill({ status: 404, json: { detail: 'Not found.' } });
    }
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (route.request().method() === 'GET') return route.fulfill({ json: [] });
    return route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
  });
}

const card = (page: Page, name: string) =>
  page
    .getByText(name, { exact: true })
    .locator('xpath=ancestor::div[contains(@class,"rounded")][1]');

/** The rule reaches the page: a restricted card carries the wash and a public one none. */
async function expectToneReaches(page: Page) {
  const restricted = card(page, 'The Pale Road');
  const plain = card(page, 'The Shroud');
  await expect(restricted).toHaveClass(/codex-restricted/);
  await expect(plain).not.toHaveClass(/codex-restricted/);
  const wash = (l: typeof restricted) => l.evaluate((el) => getComputedStyle(el).backgroundImage);
  expect(await wash(restricted)).toContain('linear-gradient');
  expect(await wash(plain)).toEqual('none');
}

test.describe('The Codex restricted reading (#4191) on the production bundle', () => {
  test('staff at a subject: no banner, restricted entries toned, no badges', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockCodex(page, 'staff');
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/codex?subject=${SUBJECT_ID}`);
    await expect(page.getByText('Where the Shroud Thins')).toBeVisible();
    await expect(page.getByText(/Staff view/)).toHaveCount(0);
    await expect(page.getByText('Ilsavet du Verane')).toHaveCount(0);
    await expectToneReaches(page);
    await page.screenshot({ path: shot('01-staff-subject-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });

  test('a one-character player: toned, no badge bearing their own name', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockCodex(page, 'player');
    await page.goto(`/codex?subject=${SUBJECT_ID}`);
    await expect(page.getByText('Where the Shroud Thins')).toBeVisible();
    await expect(page.getByText('Researching')).toBeVisible();
    await expect(page.getByText('Ilsavet du Verane')).toHaveCount(0);
    await expect(page.getByLabel('Character knowledge scope')).toHaveCount(0);
    await expectToneReaches(page);
    await page.screenshot({ path: shot('02-player-subject-1280.png'), fullPage: true });
  });

  test('a two-character player: the badges and the scope dropdown', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockCodex(page, 'two');
    await page.goto(`/codex?subject=${SUBJECT_ID}`);
    await expect(page.getByText('Where the Shroud Thins')).toBeVisible();
    await expect(page.getByLabel('Character knowledge scope')).toBeVisible();
    await expect(card(page, 'The Pale Road').getByText('Corwen Hale')).toBeVisible();
    await expectToneReaches(page);
    await page.screenshot({ path: shot('03-two-characters-subject-1280.png'), fullPage: true });
  });

  test('a restricted entry read in full, and the search results', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockCodex(page, 'player');
    await page.goto(`/codex?subject=${SUBJECT_ID}&entry=3`);
    await expect(page.getByText('The road runs north of the last milestone.')).toBeVisible();
    const plate = page
      .getByText('The Pale Road', { exact: true })
      .locator('xpath=ancestor::div[contains(@class,"codex-restricted")]');
    await expect(plate).toHaveCount(1);
    expect(await plate.evaluate((el) => getComputedStyle(el).backgroundImage)).toContain(
      'linear-gradient'
    );
    await expect(page.getByText('Known by:')).toHaveCount(0);
    await page.screenshot({ path: shot('04-entry-detail-1280.png'), fullPage: true });

    await page.getByPlaceholder('Search codex...').fill('sh');
    const results = page.getByRole('button', { name: /Shroud/ });
    await expect(results).toHaveCount(2);
    await expect(page.getByRole('button', { name: /Where the Shroud Thins/ })).toHaveClass(
      /codex-restricted/
    );
    await expect(page.getByRole('button', { name: /^The Shroud/ })).not.toHaveClass(
      /codex-restricted/
    );
    await page.screenshot({ path: shot('05-search-1280.png') });
  });

  test('phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockCodex(page, 'player');
    await page.goto(`/codex?subject=${SUBJECT_ID}`);
    await expect(page.getByText('Where the Shroud Thins')).toBeVisible();
    await expectToneReaches(page);
    await page.screenshot({ path: shot('06-player-subject-390.png'), fullPage: true });
  });
});
