import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4106: the real `/characters/create` page at Final Touches and
 * the real `/characters/:entry` sheet on the production bundle, every `/api/**` call
 * answered by fixtures shaped like the serializers.
 *
 * Three readings. At Final Touches a goal row carries the "Keep to yourself" mark and
 * pressing it rides into the draft's PATCH as `is_secret`. On the sheet the owner's
 * payload carries both goals, the secret one marked; a friend's payload (the server
 * dropped the secret goal before the tier applied) carries one. On the Ties tab a
 * membership whose house has exiled the character shows the verdict beside the house.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4106');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const DRAFT_ID = 7;
const ENTRY_ID = 1;
const SHEET_ID = 20;

// --- character creation -------------------------------------------------------------

const AREA = {
  id: 6,
  name: 'Tenebrum',
  description: 'PLACEHOLDER description, not the authored text.',
  crest_image: null,
  realm_theme: 'umbros',
  realm_slug: 'umbros',
  realm_name: 'Umbros',
  realm_formal_name: 'The Umbral Empire',
  realm_id: 3,
};

const DOMAINS = [
  { id: 1, name: 'Ambition', description: '', display_order: 1, is_optional: false },
  { id: 2, name: 'Family', description: '', display_order: 2, is_optional: false },
];

/** The draft at Final Touches: two goals already written, neither kept yet. */
function buildDraft() {
  const completion: Record<number, boolean> = {};
  for (let s = 1; s <= 11; s += 1) completion[s] = s < 10;
  return {
    id: DRAFT_ID,
    current_stage: 10,
    selected_area: AREA,
    selected_beginnings: null,
    selected_species: null,
    selected_gender: null,
    public_worship: null,
    secret_worship: null,
    second_parent_species: null,
    age: 24,
    birthday_month: null,
    birthday_day: null,
    family: null,
    selected_origin_template: null,
    family_path: '',
    claimed_kin_slot: null,
    claimed_kin_pool: null,
    selected_vacancy: null,
    served_house: null,
    defer_parents: false,
    height_band: null,
    height_inches: null,
    build: null,
    selected_path: { id: 4, name: 'Path of Whispers' },
    selected_tradition: null,
    cg_points_spent: 0,
    cg_points_remaining: 100,
    stat_bonuses: {},
    draft_data: {
      first_name: 'Kathryn',
      goals: [
        {
          domain_id: 1,
          horizon: 'long_term',
          ordinal: 1,
          points: 5,
          notes: 'Prove worthy of my house',
        },
        {
          domain_id: 2,
          horizon: 'short_term',
          ordinal: 1,
          points: 5,
          notes: 'Find out what happened to my sister',
        },
      ],
    },
    enemy_offers: [],
    enemy_price_tables: { group: {}, person: {} },
    enemy_reasons: [],
    enemy_degree_grants: {},
    introductions_offered: { first_journal: false },
    stage_completion: completion,
    stage_errors: {},
    is_complete: false,
    submitted_at: null,
    created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z',
  };
}

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

/** Answers every call the CG page makes; `patches` collects each draft PATCH body. */
async function mockCg(page: Page): Promise<{ patches: unknown[] }> {
  const patches: unknown[] = [];
  const draft = buildDraft();
  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const method = route.request().method();
    if (p === '/api/user/') {
      await route.fulfill({ json: accountPayload() });
    } else if (p === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/character-creation/can-create/') {
      await route.fulfill({ json: { can_create: true, reason: '' } });
    } else if (p === '/api/character-creation/explanations/') {
      await route.fulfill({ json: {} });
    } else if (p === '/api/character-creation/drafts/' && method === 'GET') {
      await route.fulfill({ json: [draft] });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      const body = route.request().postDataJSON();
      patches.push(body);
      await route.fulfill({
        json: { ...draft, ...body, draft_data: { ...draft.draft_data, ...body.draft_data } },
      });
    } else if (p === '/api/goals/domains/') {
      await route.fulfill({ json: DOMAINS });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/cg-points/`) {
      await route.fulfill({ json: { spent: 0, remaining: 100, budget: 100, lines: [] } });
    } else if (method === 'GET') {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
  return { patches };
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

const PUBLIC_GOAL = {
  domain: 'Ambition',
  horizon: 'long_term',
  ordinal: 1,
  points: 5,
  notes: 'Prove worthy of my house',
  is_secret: false,
};
const SECRET_GOAL = {
  domain: 'Family',
  horizon: 'short_term',
  ordinal: 1,
  points: 5,
  notes: 'Find out what happened to my sister',
  is_secret: true,
};

/** A `CharacterSheetPayload`, as the owner or as a friend the goals are open to. */
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
    goals: owner ? [PUBLIC_GOAL, SECRET_GOAL] : [PUBLIC_GOAL],
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

test.describe('Secret goals and a membership standing (#4106) on the production bundle', () => {
  test('Final Touches: a goal can be kept to yourself, and the mark rides the PATCH', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const { patches } = await mockCg(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    // Goal keys are the stage's own counter: the second goal in draft_data is key 1.
    const mark = page.getByTestId('goal-1-secret');
    await expect(mark).toHaveAttribute('aria-pressed', 'false');
    await expect(mark).toHaveText(/Keep to yourself/);
    await expect(page.getByTestId('goal-0-secret')).toHaveAttribute('aria-pressed', 'false');
    await page.screenshot({ path: shot('final-touches-unmarked-1280.png'), fullPage: true });

    await mark.click();
    await expect(mark).toHaveAttribute('aria-pressed', 'true');
    await expect(mark).toHaveText(/Kept to yourself/);
    await page.screenshot({ path: shot('final-touches-marked-1280.png'), fullPage: true });

    // Leaving the stage saves it in one PATCH; the mark is in the goal it was pressed on.
    await page.getByRole('button', { name: /^Back: / }).click();
    await expect.poll(() => patches.length).toBeGreaterThan(0);
    const saved = (
      patches[0] as { draft_data: { goals: { notes: string; is_secret?: boolean }[] } }
    ).draft_data.goals;
    expect(saved.find((g) => g.notes === 'Find out what happened to my sister')?.is_secret).toBe(
      true
    );
    expect(saved.find((g) => g.notes === 'Prove worthy of my house')?.is_secret).toBeFalsy();
    expect(errors).toEqual([]);
  });

  test('the sheet: the owner sees both goals, the secret one marked', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, true);
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Prove worthy of my house')).toBeVisible();
    await expect(page.getByText('Find out what happened to my sister')).toBeVisible();
    await expect(page.getByTestId('goal-secret')).toHaveCount(1);
    await expect(page.getByTestId('goal-secret')).toHaveText('kept to yourself');
    await page.screenshot({ path: shot('sheet-owner-goals-1280.png'), fullPage: true });
  });

  test('the sheet: a friend the goals are open to sees one, and no mark', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, false);
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Prove worthy of my house')).toBeVisible();
    await expect(page.getByText('Find out what happened to my sister')).toHaveCount(0);
    await expect(page.getByTestId('goal-secret')).toHaveCount(0);
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
    await mockCg(page);
    await page.goto('/characters/create');
    await expect(page.getByTestId('goal-1-secret')).toBeVisible();
    await page.screenshot({ path: shot('final-touches-390.png'), fullPage: true });
  });
});
