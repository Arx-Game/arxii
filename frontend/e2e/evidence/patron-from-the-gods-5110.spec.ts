import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #5110, on the production bundle with every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * The staff house page (`/staff/almanach/houses/7`): the patron question is a
 * select of the gods the server offers; picking one and saving sends the god as
 * `patron_being_id`, with no option ids; the page then reads the house's patron
 * back by the god's own name, linked to its Codex page.
 *
 * The character creation side is walked in `frontend/e2e/almanach-founder.spec.ts`,
 * which carries a patron question on its template.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '5110');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const KATTA = 7;
const CALYX = { id: 31, name: 'Calyx', description: 'Honorable combat, just war', entry: 501 };
const VEIL = { id: 32, name: 'Veil', description: 'Secrets kept', entry: 502 };

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
  selected_entry: CHARACTER,
};

/** The patron question as `charter_questions_for_house` sends it: the options are
 * the gods of its worship, and each `id` is a god's. */
const PATRON_QUESTION = {
  id: 2,
  name: 'Umbral Patron Deity',
  prompt: 'Which temple does the house stand behind?',
  min_picks: 1,
  max_picks: 1,
  sets_patron: true,
  options: [CALYX, VEIL].map((god) => ({
    id: god.id,
    name: god.name,
    description: god.description,
    target_entry_id: god.entry,
  })),
};

type Patron = { being_id: number; being_name: string; codex_entry_id: number } | null;

const houseDocument = (patron: Patron) => ({
  house: {
    id: KATTA,
    name: 'Katta',
    description: '',
    words: '',
    colors: '',
    sigil_description: '',
    house_state: 'standing',
    published_at: null,
    particle: { born: 'mar', taken_in: 'mal' },
    default_succession_law: null,
    patron,
    facets: [],
    charter_questions: [PATRON_QUESTION],
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
    realm_id: 2,
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

/** Answers the page's reads; a dispatched `almanach_edit_house` is recorded and the
 * next document read returns the patron it set, as the server's would. */
async function mockStaff(page: Page, dispatched: Record<string, unknown>[]) {
  let patron: Patron = null;
  await page.route('**/api/**', async (route: Route) => {
    const request = route.request();
    const p = new URL(request.url()).pathname;
    if (p === '/api/user/') return route.fulfill({ json: ACCOUNT });
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [CHARACTER] });
    if (p === `/api/almanach/houses/${KATTA}/document/`) {
      return route.fulfill({ json: houseDocument(patron) });
    }
    if (p.startsWith('/api/actions/characters/') && p.endsWith('/dispatch/')) {
      const body = request.postDataJSON() as { kwargs: Record<string, unknown> };
      dispatched.push(body);
      const picked = [CALYX, VEIL].find((god) => god.id === body.kwargs.patron_being_id);
      patron = picked
        ? { being_id: picked.id, being_name: picked.name, codex_entry_id: picked.entry }
        : null;
      return route.fulfill({
        json: { backend: 'registry', deferred: false, success: true, message: 'Saved.', data: {} },
      });
    }
    if (BARE_ARRAYS.includes(p)) return route.fulfill({ json: [] });
    if (request.method() === 'GET') return route.fulfill({ json: EMPTY_PAGE });
    return route.fulfill({ json: { message: 'Done.', success: true, data: null } });
  });
}

test.describe('#5110 on the production bundle', () => {
  test('staff pick a house its patron from the gods the question offers', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    const dispatched: Record<string, unknown>[] = [];
    await mockStaff(page, dispatched);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto(`/staff/almanach/houses/${KATTA}`);
    await expect(page.locator('main.chapter h3').first()).toContainText('House Katta');

    // The question is a select over the gods, nothing picked yet.
    const select = page.getByLabel('Umbral Patron Deity');
    await expect(select).toHaveValue('');
    await expect(select.locator('option')).toHaveText(['pick', 'Calyx', 'Veil']);
    await page.screenshot({ path: shot('1-staff-patron-unpicked.png'), fullPage: true });

    // Pick Veil and save: the god goes up on its own, no option ids with it.
    await select.selectOption({ label: 'Veil' });
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect.poll(() => dispatched.length).toBe(1);
    expect(dispatched[0]).toMatchObject({
      ref: { backend: 'registry', registry_key: 'almanach_edit_house' },
      kwargs: { org_id: KATTA, patron_being_id: VEIL.id },
    });
    expect(
      (dispatched[0] as { kwargs: Record<string, unknown> }).kwargs.facet_option_ids
    ).toBeUndefined();
    console.log('dispatched:', JSON.stringify(dispatched[0]));

    // Read back: the select holds Veil, named plainly and linked to its Codex page.
    await expect(select).toHaveValue(String(VEIL.id));
    const picked = page.locator('.field', { hasText: 'Umbral Patron Deity' });
    await expect(picked.getByRole('link', { name: 'Veil', exact: true })).toHaveAttribute(
      'href',
      `/codex?entry=${VEIL.entry}`
    );
    await expect(picked).toContainText('Secrets kept');
    await page.waitForTimeout(400);
    await page.screenshot({ path: shot('2-staff-patron-veil.png'), fullPage: true });
    expect(errors, errors.join('\n')).toEqual([]);
  });
});
