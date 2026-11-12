import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #5090, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * The staff house page (`/staff/almanach/houses/9`): the Particle field shows the
 * pair itself, the State control reads Active, and the record rail's links are
 * named for where they go and open the org page and the family page.
 *
 * A Codex entry (`/codex?subject=3&entry=23`): the author's blank lines between
 * paragraphs show as gaps, measured on the rendered page, and a link in the
 * middle of a sentence stays inside its paragraph.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '5090');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const HOUSE_ID = 9;
const FAMILY_ID = 4;
const SUBJECT_ID = 3;
const GLAMOUR = 23;
const VENDETTA = 24;

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

const HOUSE_DOCUMENT = {
  house: {
    id: HOUSE_ID,
    name: 'Piropa',
    description: '',
    words: '',
    colors: '',
    sigil_description: '',
    house_state: 'standing',
    published_at: null,
    particle: { born: 'aza', taken_in: 'azas' },
    default_succession_law: { name: 'Infernal Enatic - Durance', codex_entry_id: null },
    patron: null,
    facets: [],
    charter_questions: [],
    features: [],
    offices: [],
    observances: [],
  },
  family: { family_id: FAMILY_ID, nodes: [], parentage: [], unions: [] },
  household: [],
  realm: {
    sworn_to: '',
    obligation_pct: null,
    holds: 'Inferna',
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

const CODEX_PATH = [
  { type: 'category', id: 1, name: 'The World' },
  { type: 'subject', id: SUBJECT_ID, name: 'Quiddities' },
];
const SUBJECT = {
  id: SUBJECT_ID,
  name: 'Quiddities',
  description: 'What an Infernal house is known for.',
  display_order: 0,
  category: 1,
  category_name: 'The World',
  parent: null,
  parent_name: null,
  path: CODEX_PATH,
};
/** Three paragraphs separated by blank lines, the second with a link mid-sentence. */
const GLAMOUR_LORE = [
  'A house of Glamour is destined for ever higher greatness, and grandeur is its due.',
  'Glamour houses spend to match, and a house of [[Vendetta]] keeps the account of what they owe.',
  '**Imp Fact:** To describe someone as "fancy as a glam" usually means unmatched in splendor.',
].join('\n\n');

function entryListItem(id: number, name: string) {
  return {
    id,
    name,
    summary: '',
    is_public: true,
    is_featured: false,
    featured_order: null,
    subject: SUBJECT_ID,
    subject_name: 'Quiddities',
    subject_path: CODEX_PATH,
    display_order: id,
    knowledge_status: null,
    known_by: [],
    art_url: null,
    perspective_of: null,
    also_filed_under: [],
  };
}
const GLAMOUR_DETAIL = {
  ...entryListItem(GLAMOUR, 'Glamour'),
  quote: '',
  companion: null,
  lore_content: GLAMOUR_LORE,
  mechanics_content: null,
  lore_links: [
    { match_text: '[[Vendetta]]', entry_id: VENDETTA, display_text: 'Vendetta', accessible: true },
  ],
  mechanics_links: [],
  learn_threshold: 10,
  research_progress: null,
};

async function mockApi(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [CHARACTER] });
    if (p === `/api/almanach/houses/${HOUSE_ID}/document/`) {
      return route.fulfill({ json: HOUSE_DOCUMENT });
    }
    if (p === '/api/codex/categories/tree/') {
      return route.fulfill({
        json: [
          {
            id: 1,
            name: 'The World',
            description: '',
            subjects: [{ id: SUBJECT_ID, name: 'Quiddities', has_children: false, entry_count: 1 }],
          },
        ],
      });
    }
    if (p === `/api/codex/subjects/${SUBJECT_ID}/`) return route.fulfill({ json: SUBJECT });
    if (p === `/api/codex/subjects/${SUBJECT_ID}/children/`) return route.fulfill({ json: [] });
    if (p === '/api/codex/entries/') {
      if (url.searchParams.get('featured')) return route.fulfill({ json: [] });
      return route.fulfill({ json: [entryListItem(GLAMOUR, 'Glamour')] });
    }
    if (p === `/api/codex/entries/${GLAMOUR}/`) return route.fulfill({ json: GLAMOUR_DETAIL });
    if (p === '/api/roster/mail/unread-count/') return route.fulfill({ json: { count: 0 } });
    if (BARE_ARRAYS.includes(p)) return route.fulfill({ json: [] });
    if (route.request().method() === 'GET') return route.fulfill({ json: EMPTY_PAGE });
    return route.fulfill({ json: { message: 'Done.', success: true, data: null } });
  });
}

test.describe('#5090 on the production bundle', () => {
  test('the staff house page: the particles, Active, and links named for where they go', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/staff/almanach/houses/${HOUSE_ID}`);
    await expect(page.locator('main.chapter h3').first()).toContainText('House Piropa');

    // Particle: the pair itself, nothing to hover.
    const particle = page.locator('.field', { hasText: 'particle' }).locator('.val');
    await expect(particle).toHaveText('aza / azas');
    await expect(page.getByText('worked example')).toHaveCount(0);

    // State: the stored value is still `standing`; it reads Active.
    const state = page.getByLabel('State');
    await expect(state).toHaveValue('standing');
    await expect(state.locator('option:checked')).toHaveText('Active');
    await expect(state.locator('option')).toHaveText(['Active', 'In exile', 'Extinct', 'Gentry']);

    // Links: named for where they go, both real links, no dead entry.
    const org = page.getByRole('link', { name: 'Piropa org page', exact: true });
    const family = page.getByRole('link', { name: 'Piropa family page', exact: true });
    await expect(org).toHaveAttribute('href', `/orgs/${HOUSE_ID}`);
    await expect(family).toHaveAttribute('href', `/families/${FAMILY_ID}`);
    await expect(page.getByText('the organization', { exact: true })).toHaveCount(0);
    await expect(page.getByText('the house on the roster')).toHaveCount(0);

    await page.screenshot({ path: shot('1-house-page.png'), fullPage: true });

    // The family page link leaves for the family page.
    await family.click();
    await expect(page).toHaveURL(new RegExp(`/families/${FAMILY_ID}$`));
    expect(errors, errors.join('\n')).toEqual([]);
  });

  test('a Codex entry keeps the gaps between its paragraphs, and a link stays in its sentence', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockApi(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/codex?subject=${SUBJECT_ID}&entry=${GLAMOUR}`);
    const first = page.getByText('destined for ever higher greatness');
    await expect(first).toBeVisible();

    const paragraphs = first.locator('xpath=..').locator('p');
    await expect(paragraphs).toHaveCount(3);
    // The link sits inside the second paragraph, between the words around it.
    await expect(paragraphs.nth(1)).toHaveText(
      'Glamour houses spend to match, and a house of Vendetta keeps the account of what they owe.'
    );
    await expect(paragraphs.nth(1).getByRole('button', { name: 'Vendetta' })).toBeVisible();

    // The gap is measured on the page: the space between one paragraph's last line
    // and the next one's first, against the height of a line of that text.
    const boxes = await paragraphs.evaluateAll((nodes) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        return {
          top: rect.top,
          bottom: rect.bottom,
          lineHeight: parseFloat(getComputedStyle(node).lineHeight),
          marginTop: getComputedStyle(node).marginTop,
        };
      })
    );
    const gaps = [boxes[1].top - boxes[0].bottom, boxes[2].top - boxes[1].bottom];
    console.log('paragraph gaps (px):', gaps, 'line height (px):', boxes[0].lineHeight);
    console.log(
      'computed margin-top of paragraphs 2 and 3:',
      boxes[1].marginTop,
      boxes[2].marginTop
    );
    for (const gap of gaps) {
      expect(gap).toBeGreaterThanOrEqual(boxes[0].lineHeight * 0.5);
    }

    await page.screenshot({ path: shot('2-codex-paragraphs.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
