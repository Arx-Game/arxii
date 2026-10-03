import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';

/**
 * Review evidence for #4124 (Backgrounds, a life in beats): the real `/characters/create`
 * page at Lineage and the real `/characters/:entry` sheet on the production bundle, every
 * `/api/**` call answered by fixtures shaped like the serializers.
 *
 * Readings. Lineage: the house block comes first, then the beats by stage; a taken one-of
 * beat draws its answers across, a taken any-that-apply beat down; adding a beat sends
 * the whole `draft_data.beats` map; picking a one-of answer syncs one entry. The sheet:
 * the owner's payload carries beats and the page draws "Public sheet" and a "Private
 * sheet" region; a stranger's carries none and the page is the public sheet alone.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4124');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const DRAFT_ID = 9;
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
const BEGINNING = {
  id: 7,
  name: 'Nobility',
  description: 'PLACEHOLDER description.',
  art_image: null,
  allowed_species_ids: [1],
  grants_species_languages: true,
  cg_point_cost: 0,
  codex_entry_ids: [],
  heritage: null,
};
const UPBRINGING = {
  id: 190,
  max_claim_tier: '',
  name: 'Placeholder Upbringing',
  frame_narrative: 'PLACEHOLDER frame prose: the Upbringing paragraph the staff writer owns.',
  is_active: true,
  sort_order: 1,
  cg_point_cost: 0,
  allows_claim_family: false,
  allows_name_family: false,
  allows_no_family: true,
  parentage: 'unknown',
  parentage_note: '',
  claimable_kind_ids: [],
  family_templates: [],
  slots: [],
};
const TAROT = [
  {
    id: 1,
    name: 'The Fool',
    arcana_type: 'major',
    rank: 0,
    latin_name: 'Fatui',
    upright_meaning: '',
    reversed_meaning: '',
    image: null,
  },
];

/** The beat pool as the draft meets it (`GET .../beats/`). */
function beatPool(taken: Record<string, { taken?: boolean; unknown?: boolean; line?: string }>) {
  const state = (id: number) => taken[String(id)] ?? {};
  return [
    {
      beat_id: 1,
      name: 'The household',
      prompt: 'PLACEHOLDER prompt for the household beat.',
      life_stage: 'childhood',
      selection: 'one_of',
      taken: Boolean(state(1).taken),
      unknown: Boolean(state(1).unknown),
      line: state(1).line ?? '',
      answer_offer_ids: [10, 11],
      kept: false,
    },
    {
      beat_id: 2,
      name: 'The first rule',
      prompt: 'PLACEHOLDER prompt for the first-rule beat.',
      life_stage: 'youth',
      selection: 'one_of',
      taken: Boolean(state(2).taken),
      unknown: Boolean(state(2).unknown),
      line: state(2).line ?? '',
      answer_offer_ids: [20],
      kept: false,
    },
    {
      beat_id: 3,
      name: 'The work',
      prompt: 'PLACEHOLDER prompt for the work beat.',
      life_stage: 'adulthood',
      selection: 'any',
      taken: Boolean(state(3).taken),
      unknown: Boolean(state(3).unknown),
      line: state(3).line ?? '',
      answer_offer_ids: [30, 31],
      kept: false,
    },
  ];
}

function offer(
  offer_id: number,
  beat: number,
  name: string,
  distinction_id: number,
  cost_per_rank: number
) {
  return {
    offer_id,
    distinction_id,
    name,
    player_line: 'PLACEHOLDER gloss.',
    chapter: 'backgrounds',
    arrives_as: 'choice',
    opener_label: '',
    cost_per_rank,
    max_rank: 1,
    is_locked: false,
    lock_reason: '',
    opener_key: `beat:${beat}`,
    first_look: false,
    held: false,
    effect_line: '',
    taken_per_feature: false,
    opens_feature: false,
    requires_feature_opened: false,
    cg_max_rank: 0,
  };
}
const OFFERS = [
  offer(10, 1, 'Patient', 100, 10),
  offer(11, 1, 'Spoiled', 101, -10),
  offer(20, 2, 'Wrathful', 200, -5),
  offer(30, 3, 'Efficient', 300, 10),
  offer(31, 3, 'Secretive', 301, 25),
];

function buildDraft(beats: Record<string, { taken?: boolean; unknown?: boolean; line?: string }>) {
  const completion: Record<number, boolean> = {};
  for (let s = 1; s <= 11; s += 1) completion[s] = s < 3;
  return {
    id: DRAFT_ID,
    current_stage: 3,
    selected_area: AREA,
    selected_beginnings: BEGINNING,
    selected_species: { id: 1, name: 'Human', description: '' },
    selected_gender: { id: 2, key: 'female', display_name: 'Female' },
    public_worship: null,
    secret_worship: null,
    second_parent_species: null,
    age: 24,
    birthday_month: null,
    birthday_day: null,
    family: null,
    selected_origin_template: UPBRINGING,
    family_path: 'none',
    claimed_kin_slot: null,
    claimed_kin_pool: null,
    selected_vacancy: null,
    served_house: null,
    defer_parents: false,
    height_band: null,
    height_inches: null,
    build: null,
    selected_path: null,
    selected_tradition: null,
    cg_points_spent: 0,
    cg_points_remaining: 100,
    stat_bonuses: {},
    draft_data: { beats, tarot_card_name: 'The Fool' },
    stage_completion: completion,
    stage_errors: {},
    has_existing_characters: false,
    stats_points_remaining: 0,
    stats_budget: 0,
    starting_technique_picks: 0,
    age_min: 16,
    age_max: 60,
    bundled_distinctions: [],
    derived_anchors: {},
    enemy_offers: [],
    enemy_price_tables: { group: {}, person: {} },
    enemy_degree_grants: {},
    enemy_reasons: [],
    introductions_offered: { first_journal: false },
    is_complete: false,
    submitted_at: null,
    created_at: '2026-10-03T00:00:00Z',
    updated_at: '2026-10-03T00:00:00Z',
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

/** Answers every call the CG page makes; `patches` and `syncs` collect the writes. */
/** The one beat a blank-slate Beginning keeps (`beat_mode = one_kept`): taken by the
 * Beginning, never removed, nothing else in the pool. */
const KEPT_POOL = [
  {
    beat_id: 9,
    name: 'Defining the Inexplicable',
    prompt: 'PLACEHOLDER prompt for the kept beat.',
    life_stage: 'at_the_glimpse',
    selection: 'any',
    taken: true,
    unknown: false,
    line: '',
    answer_offer_ids: [90, 91],
    kept: true,
  },
];
const KEPT_OFFERS = [offer(90, 9, 'Assassin', 900, 10), offer(91, 9, 'Magical Scar', 901, 5)];

async function mockCg(
  page: Page,
  mode: 'pool' | 'one_kept' = 'pool'
): Promise<{ patches: unknown[]; syncs: unknown[] }> {
  const patches: unknown[] = [];
  const syncs: unknown[] = [];
  let beats: Record<string, { taken?: boolean; unknown?: boolean; line?: string }> =
    mode === 'one_kept'
      ? {}
      : {
          '1': { taken: true },
          '3': { taken: true, line: 'PLACEHOLDER line under the work beat.' },
        };
  const draft = buildDraft(beats);
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
      const body = route.request().postDataJSON() as { draft_data?: { beats?: typeof beats } };
      patches.push(body);
      if (body.draft_data?.beats) {
        beats = body.draft_data.beats;
        draft.draft_data = { ...draft.draft_data, beats };
      }
      await route.fulfill({ json: draft });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/beats/`) {
      await route.fulfill({ json: mode === 'one_kept' ? KEPT_POOL : beatPool(beats) });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/offers/`) {
      const chapter = url.searchParams.get('chapter');
      // A beat's answers are open only while the beat is taken and not unknown, the
      // way `_opener_satisfied` filters them on the server.
      let offers: typeof OFFERS = [];
      if (chapter === 'backgrounds' && mode === 'one_kept') {
        offers = KEPT_OFFERS;
      } else if (chapter === 'backgrounds') {
        offers = OFFERS.filter((o) => {
          const id = Number(o.opener_key.split(':')[1]);
          return Boolean(beats[String(id)]?.taken) && !beats[String(id)]?.unknown;
        });
      }
      await route.fulfill({ json: { offers, closed: [] } });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/sync/`) {
      syncs.push(route.request().postDataJSON());
      await route.fulfill({ json: { distinctions: [] } });
    } else if (p === `/api/distinctions/drafts/${DRAFT_ID}/distinctions/`) {
      // The draft already holds Patient from the household beat and Efficient from the
      // work beat, so the captures show a picked one-of card and a ticked row.
      await route.fulfill({
        json:
          mode === 'one_kept'
            ? []
            : [
                {
                  id: 100,
                  distinction_id: 100,
                  distinction_name: 'Patient',
                  rank: 1,
                  cost: 10,
                  offer_ids: [10],
                  sources: ['The household'],
                  arrivals: ['choice'],
                  feature_trait: '',
                  feature_marking: 0,
                },
                {
                  id: 300,
                  distinction_id: 300,
                  distinction_name: 'Efficient',
                  rank: 1,
                  cost: 10,
                  offer_ids: [30],
                  sources: ['The work'],
                  arrivals: ['choice'],
                  feature_trait: '',
                  feature_marking: 0,
                },
              ],
      });
    } else if (p === '/api/character-creation/origin-templates/') {
      await route.fulfill({ json: [UPBRINGING] });
    } else if (p === '/api/character-creation/tarot-cards/') {
      await route.fulfill({ json: TAROT });
    } else if (p === '/api/character-creation/naming-ritual-config/') {
      await route.fulfill({ json: { flavor_text: '', codex_entry_id: null } });
    } else if (p === `/api/character-creation/drafts/${DRAFT_ID}/cg-points/`) {
      await route.fulfill({
        json: {
          starting_budget: 100,
          spent: 0,
          remaining: 100,
          xp_conversion_rate: 1,
          breakdown: [],
        },
      });
    } else if (p === '/api/character-creation/genders/') {
      await route.fulfill({ json: [{ id: 2, key: 'female', display_name: 'Female' }] });
    } else if (p === '/api/almanach/houses/' || p === '/api/worship/beings/') {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    } else if (method === 'GET') {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
  return { patches, syncs };
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
const BEATS = [
  {
    beat_id: 1,
    name: 'The household',
    life_stage: 'childhood',
    prompt: '',
    unknown: false,
    line: 'PLACEHOLDER line the player wrote.',
    answers: ['Patient'],
  },
  {
    beat_id: 3,
    name: 'The work',
    life_stage: 'adulthood',
    prompt: '',
    unknown: false,
    line: '',
    answers: ['Efficient', 'Secretive'],
  },
  {
    beat_id: 2,
    name: 'The first rule',
    life_stage: 'youth',
    prompt: '',
    unknown: true,
    line: '',
    answers: [],
  },
];

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
    story: {
      background: 'PLACEHOLDER told background: the paragraph drafted from the beats, then edited.',
      origin_story_state: 'NOT_STARTED',
      origin_slots: [],
    },
    actor_sheet: {
      never_do: 'Strike first at a table.',
      protect: '',
      fear: '',
      enemy_public_line: '',
      enemy: null,
      introductions: [],
    },
    goals: [],
    beats: owner ? BEATS : [],
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

test.describe('Backgrounds, a life in beats (#4124) on the production bundle', () => {
  test('Lineage: the house first, then the beats; one-of across, any-that-apply down', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    const { patches, syncs } = await mockCg(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/characters/create');

    const household = page.getByRole('article', { name: 'The household' });
    await expect(household).toBeVisible();
    await expect(household.getByRole('list')).toHaveClass(/oneof/);
    await expect(household.getByRole('button', { name: /Patient/ })).toBeVisible();
    await expect(household.getByRole('button', { name: /Patient/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(household.getByRole('button', { name: /Spoiled/ })).toBeVisible();
    await expect(household.getByText('One of')).toBeVisible();
    const work = page.getByRole('article', { name: 'The work' });
    await expect(work.getByRole('list')).not.toHaveClass(/oneof/);
    await expect(work.getByRole('button', { name: /Efficient/ })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(work.getByText('Any that apply')).toBeVisible();
    // The youth beat waits in its pool; the house block sits above every beat.
    const youthPool = page.getByRole('group', { name: /Add a beat: Youth/ });
    await expect(youthPool.getByRole('button', { name: 'The first rule' })).toBeVisible();
    const houseBox = await page
      .getByRole('heading', { name: /Lineage|Upbringing/i })
      .first()
      .boundingBox();
    const beatBox = await household.boundingBox();
    expect(houseBox && beatBox && houseBox.y < beatBox.y).toBeTruthy();
    await page.screenshot({ path: shot('lineage-beats-1280.png'), fullPage: true });

    // Adding a beat sends the whole map; the new beat opens with its answers.
    await youthPool.getByRole('button', { name: 'The first rule' }).click();
    await expect.poll(() => patches.length).toBeGreaterThan(0);
    const sent = (patches.at(-1) as { draft_data: { beats: Record<string, unknown> } }).draft_data
      .beats;
    expect(Object.keys(sent).sort()).toEqual(['1', '2', '3']);
    const firstRule = page.getByRole('article', { name: 'The first rule' });
    await expect(firstRule.getByRole('button', { name: /Wrathful/ })).toBeVisible();
    await page.screenshot({ path: shot('lineage-beat-added-1280.png'), fullPage: true });

    // A one-of answer syncs one entry.
    await household.getByRole('button', { name: /Spoiled/ }).click();
    await expect.poll(() => syncs.length).toBeGreaterThan(0);
    const synced = (syncs.at(-1) as { distinctions: { offer_id: number }[] }).distinctions;
    // Spoiled replaces Patient on the one-of beat; Efficient on the work beat stays.
    expect(synced.map((d) => d.offer_id).sort()).toEqual([11, 30]);
    expect(errors).toEqual([]);
  });

  test('the sheet: the owner reads the public sheet and the private sheet', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, true);
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByRole('heading', { name: 'Public sheet' })).toBeVisible();
    const region = page.getByRole('region', { name: 'Private sheet' });
    await expect(region.getByText('The household')).toBeVisible();
    await expect(region.getByText('Patient')).toBeVisible();
    await expect(region.getByText('Efficient, Secretive')).toBeVisible();
    await expect(region.getByText('The first rule')).toBeVisible();
    await expect(page.getByText(/yours and staff/i)).toHaveCount(0);
    await page.screenshot({ path: shot('sheet-owner-private-1280.png'), fullPage: true });
  });

  test('the sheet: an unknown beat reads Unknown on the private sheet', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, true);
    await page.goto(`/characters/${ENTRY_ID}`);
    const region = page.getByRole('region', { name: 'Private sheet' });
    await expect(region.getByText('The first rule')).toBeVisible();
    await expect(region.getByText('Unknown')).toBeVisible();
  });

  test('the sheet: a stranger gets the public sheet alone', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockSheet(page, false);
    await page.goto(`/characters/${ENTRY_ID}`);
    await expect(page.getByText('Strike first at a table.')).toBeVisible();
    await expect(page.getByRole('region', { name: 'Private sheet' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Public sheet' })).toHaveCount(0);
    await page.screenshot({ path: shot('sheet-stranger-1280.png'), fullPage: true });
  });

  test('Lineage: a Sleeper keeps one beat, with nothing to add and nothing to remove', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockCg(page, 'one_kept');
    await page.goto('/characters/create');
    const kept = page.getByRole('article', { name: 'Defining the Inexplicable' });
    await expect(kept).toBeVisible();
    await expect(kept.getByRole('button', { name: /Assassin/ })).toBeVisible();
    await expect(kept.getByRole('button', { name: /Magical Scar/ })).toBeVisible();
    await expect(kept.getByRole('button', { name: 'Remove' })).toHaveCount(0);
    await expect(page.getByRole('group', { name: /Add a beat/ })).toHaveCount(0);
    await page.screenshot({ path: shot('lineage-sleeper-1280.png'), fullPage: true });
  });

  test('at phone width', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1100 });
    await mockCg(page);
    await page.goto('/characters/create');
    await expect(page.getByRole('article', { name: 'The household' })).toBeVisible();
    await page.screenshot({ path: shot('lineage-beats-390.png'), fullPage: true });
  });
});
