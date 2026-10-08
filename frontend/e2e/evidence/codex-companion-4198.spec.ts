import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4198: the real `/codex` entry page on the production bundle, every
 * `/api/**` call answered by fixtures shaped like the serializers, the two gods carrying
 * the rows of the approved demo (version 3).
 *
 * Readings: the Fleshreaper read by staff (the rail beside the Lore, the feast day and the
 * feud as sections under it); Calyx read by the same staff (her own side of the feud); Calyx
 * read by a player who cannot see the Fleshreaper (no feud line, no feud section); the
 * Fleshreaper at phone width (the rail folds under the prose).
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4198');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

type Viewer = 'staff' | 'stranger';
const SUBJECT_ID = 3;
const FLESHREAPER = 1;
const CALYX = 2;

const PATH = [
  { type: 'category', id: 1, name: 'The World' },
  { type: 'subject', id: SUBJECT_ID, name: 'Gods' },
];
const TREE = [
  {
    id: 1,
    name: 'The World',
    description: 'The lands, the roads between them, and what lies past the last of them.',
    subjects: [{ id: SUBJECT_ID, name: 'Gods', has_children: false, entry_count: 2 }],
  },
];
const SUBJECT = {
  id: SUBJECT_ID,
  name: 'Gods',
  description: 'The pantheon.',
  display_order: 0,
  category: 1,
  category_name: 'The World',
  parent: null,
  parent_name: null,
  path: PATH,
};

const FLESHREAPER_LORE = [
  'The Fleshreaper is commonly perceived to be the patron goddess of the Lycans. While it is true that a great majority of her worshippers and her largest temple is in Ariwn, the Gory Goddess does have a surprising number of her faithful scattered through the rest of Catenys.',
  "Goddess of savagery and bloodthirsty carnage, many lycans host great prayer ceremonies before battles, hoping that she will inspire them and act through them. Conversely in Aythirmok, berserkers often pray to the Fleshreaper that she might 'stay her claws' and grant them control when needed.",
  'While few claim to have ever seen the Fleshreaper manifest, legend has it that she appears as a heavily armored tiefling in platemail and carrying a scythe.',
].join('\n\n');
const CALYX_LORE = [
  'Heir to the mantle of Gloria, Calyx is the goddess of honorable combat, defense of the innocent, fierce idealism, and chivalry. While many knightly orders are in her name, and few at war fail to give her homage, she has relatively few true adherents.',
  'Very few claim to have ever seen Calyx manifest in the flesh, but it is said she appears as a lovely young woman of slight frame, rose colored hair, and fiercely determined eyes.',
].join('\n\n');
const CALYX_QUOTE =
  "It is not a contradiction when knights on both sides of the battlefield pray and ask Calyx for guidance. It would be if they asked for victory, but if they are truly one of hers, it's not what they ask. They ask that in their darkest moments, they have the strength to continue to do what's right.";

const item = (text: string, extra: { entry_id?: number; anchor?: string } = {}) => ({
  text,
  entry_id: extra.entry_id ?? null,
  anchor: extra.anchor ?? null,
});

/** The Fleshreaper's companion as the provider builds it; the feud only when Calyx is visible. */
function fleshreaperCompanion(seesCalyx: boolean) {
  const rail = [
    { label: 'Domains', items: [item('Carnage, Hunters, Lycans, Bestial Savagery, Bloodthirst')] },
    {
      label: 'Also called',
      items: [
        item('Our Lady of Visceral Violence (Infernal)'),
        item('She of the Bloody Banquet'),
        item('She of the Crimson Carnage'),
        item('The Gory Goddess'),
      ],
    },
    {
      label: 'Feast days',
      items: [item('The Reaping Festival · Masquing 18 (10/18)', { anchor: 'feast-10-18' })],
    },
    { label: 'Cards', items: [item('Death'), item('The Tower reversed')] },
    { label: 'Favored', items: [item('Saevus')] },
    { label: 'Associated', items: [item('Praedari'), item('Tremora')] },
  ];
  const sections = [
    {
      anchor: 'feast-10-18',
      label: 'Feast day',
      name: 'The Reaping Festival',
      when: 'Masquing 18 (10/18)',
      entry_id: null,
      body: 'The Festival of the Fleshreaper is generally more mild than most would expect in Ariwn and most lands, with Lycans typically celebrating it with grand hunts and a massive feast of generally undercooked meat.',
    },
  ];
  if (seesCalyx) {
    rail.push({
      label: 'Feud',
      items: [item('Calyx', { entry_id: CALYX, anchor: `relationship-${CALYX}` })],
    });
    sections.push({
      anchor: `relationship-${CALYX}`,
      label: 'Feud',
      name: 'Calyx',
      when: null,
      entry_id: CALYX,
      body: 'Placeholder for shape: the Fleshreaper tells the feud her own way on her page.',
    });
  }
  return { rail, sections };
}

function calyxCompanion(seesFleshreaper: boolean) {
  const rail = [
    {
      label: 'Domains',
      items: [item('Honorable Combat, Just War, Chivalry, Defense of the Innocent and Weak')],
    },
    {
      label: 'Also called',
      items: [item('The Brave'), item('The Defender'), item('The One True Knight (Inferna)')],
    },
    {
      label: 'Feast days',
      items: [item('The Vigil of the Sword · Unyielding 1 (9/1)', { anchor: 'feast-9-1' })],
    },
    { label: 'Favored', items: [item('Fortis')] },
    { label: 'Associated', items: [item('Fidelis'), item('Firma'), item('Honoris')] },
  ];
  const sections = [
    {
      anchor: 'feast-9-1',
      label: 'Feast day',
      name: 'The Vigil of the Sword',
      when: 'Unyielding 1 (9/1)',
      entry_id: null,
      body: "On the first eve of the Month of the Unyielding there is a vigil held in honor of Calyx and Gloria, in remembrance of the month long battle that the two waged against the forces of the Abyss in the Gods War. Calyx's priests often hold a sermon titled 'Why We Fight'.",
    },
  ];
  if (seesFleshreaper) {
    rail.push({
      label: 'Feud',
      items: [
        item('The Fleshreaper', { entry_id: FLESHREAPER, anchor: `relationship-${FLESHREAPER}` }),
      ],
    });
    sections.push({
      anchor: `relationship-${FLESHREAPER}`,
      label: 'Feud',
      name: 'The Fleshreaper',
      when: null,
      entry_id: FLESHREAPER,
      body: "While holding that she is not above redemption, it is felt that Calyx believes that the Fleshreaper's nature inclines her faithful to fall woefully short in honorable conduct, and that any of Calyx's faithful should strive to show them the better way.",
    });
  }
  return { rail, sections };
}

interface Seed {
  id: number;
  name: string;
  summary: string;
  is_public: boolean;
  quote: string;
  lore: string;
  companion: (viewer: Viewer) => ReturnType<typeof fleshreaperCompanion>;
}
/** The Fleshreaper is restricted: a stranger never sees her, so Calyx's feud is not drawn. */
const SEEDS: Seed[] = [
  {
    id: FLESHREAPER,
    name: 'The Fleshreaper',
    summary: 'Goddess of savagery and carnage.',
    is_public: false,
    quote: '',
    lore: FLESHREAPER_LORE,
    companion: () => fleshreaperCompanion(true),
  },
  {
    id: CALYX,
    name: 'Calyx',
    summary: 'Goddess of honorable combat.',
    is_public: true,
    quote: CALYX_QUOTE,
    lore: CALYX_LORE,
    companion: (viewer) => calyxCompanion(viewer === 'staff'),
  },
];

function listItem(seed: Seed) {
  return {
    id: seed.id,
    name: seed.name,
    summary: seed.summary,
    is_public: seed.is_public,
    is_featured: false,
    featured_order: null,
    subject: SUBJECT_ID,
    subject_name: 'Gods',
    subject_path: PATH,
    display_order: seed.id,
    knowledge_status: null,
    known_by: [],
    art_url: null,
    perspective_of: null,
    also_filed_under: [],
  };
}
function detail(seed: Seed, viewer: Viewer) {
  return {
    ...listItem(seed),
    quote: seed.quote,
    companion: seed.companion(viewer),
    lore_content: seed.lore,
    mechanics_content: null,
    lore_links: [],
    mechanics_links: [],
    learn_threshold: 10,
    research_progress: null,
  };
}
function visible(viewer: Viewer) {
  return SEEDS.filter((s) => viewer === 'staff' || s.is_public);
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
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [] });
    if (p === '/api/codex/categories/tree/') return route.fulfill({ json: TREE });
    if (p === `/api/codex/subjects/${SUBJECT_ID}/`) return route.fulfill({ json: SUBJECT });
    if (p === `/api/codex/subjects/${SUBJECT_ID}/children/`) return route.fulfill({ json: [] });
    if (p === '/api/codex/entries/') {
      if (url.searchParams.get('featured')) return route.fulfill({ json: [] });
      return route.fulfill({ json: visible(viewer).map(listItem) });
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

const rail = (page: Page) => page.getByLabel('At a glance');
const columns = (page: Page) =>
  page
    .locator('.codex-with-rail')
    .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' ').length);

test.describe('The Codex companion (#4198) on the production bundle', () => {
  test('the Fleshreaper, read by staff: the rail beside the Lore, the stories under it', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    await mockCodex(page, 'staff');
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/codex?subject=${SUBJECT_ID}&entry=${FLESHREAPER}`);
    await expect(page.getByText('patron goddess of the Lycans')).toBeVisible();
    await expect(rail(page)).toBeVisible();
    await expect(rail(page)).toContainText('Domains');
    await expect(rail(page)).toContainText(
      'Carnage, Hunters, Lycans, Bestial Savagery, Bloodthirst'
    );
    await expect(rail(page)).toContainText('The Gory Goddess');
    await expect(rail(page)).toContainText('Death, The Tower reversed');
    await expect(rail(page)).toContainText('Saevus');
    await expect(rail(page)).toContainText('Praedari, Tremora');
    await expect(rail(page).getByRole('button', { name: 'Calyx' })).toBeVisible();
    expect(await columns(page)).toBe(2);
    const feast = page.locator('#feast-10-18');
    await expect(feast).toContainText('Feast day');
    await expect(feast).toContainText('The Reaping Festival');
    await expect(feast).toContainText('Masquing 18 (10/18)');
    await expect(feast).toContainText('grand hunts');
    await expect(page.locator(`#relationship-${CALYX}`)).toContainText('Feud');
    await page.screenshot({ path: shot('01-fleshreaper-staff-1280.png'), fullPage: true });
    expect(errors).toEqual([]);

    // The rail's feast-day line is a link down to its section.
    await rail(page)
      .getByRole('link', { name: /The Reaping Festival/ })
      .click();
    await expect(feast).toBeInViewport();
    // The feud line opens Calyx.
    await rail(page).getByRole('button', { name: 'Calyx' }).click();
    await expect(page).toHaveURL(/entry=2/);
    await expect(page.getByText('Heir to the mantle of Gloria')).toBeVisible();
    await expect(page.getByText(CALYX_QUOTE)).toBeVisible();
    await expect(page.locator(`#relationship-${FLESHREAPER}`)).toContainText(
      'not above redemption'
    );
    await page.screenshot({ path: shot('02-calyx-staff-1280.png'), fullPage: true });
  });

  test('Calyx, read by someone who cannot see the Fleshreaper: no feud line, no section', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    await mockCodex(page, 'stranger');
    await page.goto(`/codex?subject=${SUBJECT_ID}&entry=${CALYX}`);
    await expect(page.getByText('Heir to the mantle of Gloria')).toBeVisible();
    await expect(rail(page)).toContainText('Fortis');
    await expect(rail(page)).not.toContainText('Feud');
    await expect(rail(page)).not.toContainText('Fleshreaper');
    await expect(page.locator(`#relationship-${FLESHREAPER}`)).toHaveCount(0);
    await expect(page.locator('#feast-9-1')).toContainText('The Vigil of the Sword');
    await page.screenshot({ path: shot('03-calyx-stranger-1280.png'), fullPage: true });
  });

  test('phone width: the rail folds under the prose', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockCodex(page, 'staff');
    await page.goto(`/codex?subject=${SUBJECT_ID}&entry=${FLESHREAPER}`);
    const lore = page.getByText('patron goddess of the Lycans');
    await expect(lore).toBeVisible();
    await expect(rail(page)).toBeVisible();
    expect(await columns(page)).toBe(1);
    const loreBox = (await lore.boundingBox())!;
    const railBox = (await rail(page).boundingBox())!;
    expect(railBox.y).toBeGreaterThan(loreBox.y + loreBox.height);
    expect(loreBox.width).toBeGreaterThan(240);
    await page.screenshot({ path: shot('04-fleshreaper-390.png'), fullPage: true });
  });
});
