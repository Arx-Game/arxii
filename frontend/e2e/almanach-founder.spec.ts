import { test, expect, type Route } from '@playwright/test';

/**
 * Founder journey e2e (#3983 Plan B Task 7): a CG founder with an Upbringing
 * that allows a claim opens character creation at the Lineage stage, defines
 * a house on the demo duchy the founder seed plants (`_seed_demo_founder_ladder`,
 * `world/seeds/houses.py`), fills House/Family/Land/Estate, and submits.
 *
 * Every REST surface the founder journey reads is mocked here (no live
 * backend, no WebSocket — the Almanach founder flow is REST-only), following
 * `game-entry.spec.ts`'s account/roster mock plus a 404 fallback for
 * anything unlisted. Playwright specs are standalone files (see
 * `account-settings.spec.ts`), so fixture shapes are copied rather than
 * imported from `character-creation/__tests__/fixtures.ts`.
 *
 * Names mirror the real demo seed (`world/seeds/houses.py`:
 * `OVERLORDSHIP_TITLE_NAME`/`DEMO_DUCHY_NAME`/`DEMO_COUNTY_NAME`) so this
 * spec reads as exercising the actual seeded scenario, not an arbitrary one.
 */

const DRAFT_ID = 501;
const REALM_ID = 30;

// Ladder rows (#3983 Plan B Task 7 demo ladder): a Kingdom-tier rung the demo
// house holds, an unclaimed duchy chain under it, one loose barony inside the
// duchy's own county, and a sibling county with its own seat barony — the
// exact shape `_seed_demo_founder_ladder` plants and `claim_grants`/ADR-0315
// describe. Field names/shapes mirror `almanach_reads.LadderRow`.
const OVERLORDSHIP_ID = 200;
const DUCHY_ID = 201;
const DUCHY_COUNTY_ID = 202; // internal chain member, never independently claimable
const DUCHY_BARONY_ID = 203; // the duchy's own seat, internal
const LOOSE_BARONY_ID = 204; // undefined, swallowed into a duchy claim (ADR-0315)
const SECOND_COUNTY_ID = 205; // independently claimable, NOT swallowed by the duchy claim
const SECOND_COUNTY_BARONY_ID = 206;

const HOUSE_NAME = 'House Veyrane PLACEHOLDER';
const DUCHY_NAME = 'Duchy of Ashgrave PLACEHOLDER';
const COUNTY_NAME = 'County of Millhaven PLACEHOLDER';

const LADDER_ROWS = [
  {
    title_id: OVERLORDSHIP_ID,
    name: 'Veyrane Overlordship PLACEHOLDER',
    is_defined: true,
    tier: 'kingdom',
    level: 0,
    parent_title_id: null,
    house_id: 10,
    house_name: HOUSE_NAME,
    state: 'Held',
    is_seat_of: '',
    sworn_to: '',
    demesne: 1,
    vassals: 1,
    claimable: false,
    seat_domain_id: 1000,
    comes_with: '',
  },
  {
    title_id: DUCHY_ID,
    name: DUCHY_NAME,
    is_defined: true,
    tier: 'duchy',
    level: 1,
    parent_title_id: OVERLORDSHIP_ID,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: HOUSE_NAME,
    demesne: 1,
    vassals: 1,
    claimable: true,
    seat_domain_id: 1001,
    comes_with: '',
  },
  {
    title_id: DUCHY_COUNTY_ID,
    name: '',
    is_defined: false,
    tier: 'county',
    level: 2,
    parent_title_id: DUCHY_ID,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: DUCHY_NAME,
    demesne: 0,
    vassals: 1,
    claimable: true,
    seat_domain_id: 1001,
    comes_with: DUCHY_NAME,
  },
  {
    title_id: DUCHY_BARONY_ID,
    name: '',
    is_defined: false,
    tier: 'barony',
    level: 3,
    parent_title_id: DUCHY_COUNTY_ID,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: DUCHY_NAME,
    demesne: 0,
    vassals: 0,
    claimable: true,
    seat_domain_id: 1001,
    comes_with: DUCHY_NAME,
  },
  {
    title_id: LOOSE_BARONY_ID,
    name: '',
    is_defined: false,
    tier: 'barony',
    level: 3,
    parent_title_id: DUCHY_COUNTY_ID,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: HOUSE_NAME,
    demesne: 0,
    vassals: 0,
    claimable: true,
    seat_domain_id: 1002,
    comes_with: '',
  },
  {
    title_id: SECOND_COUNTY_ID,
    name: COUNTY_NAME,
    is_defined: true,
    tier: 'county',
    level: 2,
    parent_title_id: DUCHY_ID,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: HOUSE_NAME,
    demesne: 1,
    vassals: 0,
    claimable: true,
    seat_domain_id: 1003,
    comes_with: '',
  },
  {
    title_id: SECOND_COUNTY_BARONY_ID,
    name: '',
    is_defined: false,
    tier: 'barony',
    level: 3,
    parent_title_id: SECOND_COUNTY_ID,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: COUNTY_NAME,
    demesne: 0,
    vassals: 0,
    claimable: true,
    seat_domain_id: 1003,
    comes_with: COUNTY_NAME,
  },
];

const UNCLAIMED_BY_TIER = { empire: 0, kingdom: 0, duchy: 1, march: 0, county: 1, barony: 2 };

const TEMPLATE = {
  id: 70,
  name: 'Charter of Ashgrave PLACEHOLDER',
  description: 'PLACEHOLDER: the standard charter for a landed duchy of Arx.',
  kind: 2,
  name_pattern: '.*',
  mercy_min: -5,
  mercy_max: 5,
  method_min: -5,
  method_max: 5,
  status_min: -5,
  status_max: 5,
  change_min: -5,
  change_max: 5,
  allegiance_min: -5,
  allegiance_max: 5,
  power_min: -5,
  power_max: 5,
  aspect_definitions: [] as unknown[],
  features: [] as unknown[],
  holdings: [] as unknown[],
  default_succession_law: null,
  starting_kin_slots: 3,
};

const CHARTER = {
  succession_law: { name: 'Veyrane Primogeniture PLACEHOLDER', codex_entry_id: null },
  particle: { born: '', taken_in: '' },
  quiddity_prompt: '',
  capital_name: 'Arx City PLACEHOLDER',
};

// The draft opens already at Lineage (stage 3) with an area/heritage/
// Upbringing picked and no family yet — the same shape as
// `__tests__/fixtures.ts`'s `mockDraftWithUpbringing`, hand-copied here
// (standalone spec file convention, `account-settings.spec.ts`).
// `claimable_kind_ids: []` deliberately (not the real content shape) so
// `showHouseFounding` (`FamilyPathSection.tsx`) is true without also having
// to mock a non-empty claimable-family list — the founder panel is what
// this journey exercises, not the ordinary claim-a-staff-family list.
function buildDraft() {
  return {
    id: DRAFT_ID,
    current_stage: 3,
    selected_area: {
      id: 1,
      name: 'Arx City',
      description: 'The great capital city, a hub of politics and intrigue.',
      crest_image: null,
      realm_theme: 'arx',
      realm_slug: 'arx',
      realm_name: 'Arx',
      realm_id: REALM_ID,
    },
    selected_beginnings: {
      id: 1,
      name: 'Ward of the House',
      description: 'Raised a ward of a noble house.',
      art_image: null,
      allowed_species_ids: [1, 2],
      grants_species_languages: true,
      cg_point_cost: 0,
      codex_entry_ids: [],
      heritage: null,
    },
    selected_species: { id: 1, name: 'Human', description: '' },
    selected_gender: { id: 2, key: 'female', display_name: 'Female' },
    public_worship: null,
    secret_worship: null,
    second_parent_species: null,
    age: 25,
    birthday_month: null,
    birthday_day: null,
    family: null,
    selected_origin_template: {
      id: 102,
      max_claim_tier: '',
      name: 'Ward of the House',
      frame_narrative: 'You grew up a ward of a noble house, claimed as one of its own.',
      is_active: true,
      sort_order: 2,
      cg_point_cost: 0,
      allows_claim_family: true,
      allows_name_family: false,
      allows_no_family: false,
      claimable_kind_ids: [] as number[],
      family_templates: [] as unknown[],
      slots: [] as unknown[],
    },
    family_path: 'claimed',
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
    draft_data: {},
    stage_completion: {
      1: true,
      2: true,
      3: true,
      4: false,
      5: false,
      6: false,
      7: false,
      8: false,
      9: false,
      10: false,
      11: false,
    },
    has_existing_characters: false,
    stage_errors: {},
    stats_points_remaining: 5,
    stats_budget: 5,
    starting_technique_picks: 1,
    age_min: 18,
    age_max: 65,
    bundled_distinctions: [],
    derived_anchors: {},
    enemy_offers: [],
    enemy_price_tables: { group: {}, person: {} },
    enemy_degree_grants: {},
    enemy_reasons: [],
    introductions_offered: {},
  };
}

test('a founder claims the demo duchy and submits a house claim', async ({ page }) => {
  const draft = buildDraft();
  let houseClaim: Record<string, unknown> | null = null;
  let postedPayload: Record<string, unknown> | null = null;

  await page.route('**/api/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();

    if (path === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'founder-e2e',
          display_name: 'Founder E2E',
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
        },
      });
    } else if (path === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [] });
    } else if (path === '/api/backgrounds/') {
      await route.fulfill({ json: [] });
    } else if (path === '/api/character-creation/can-create/') {
      await route.fulfill({ json: { can_create: true, reason: '' } });
    } else if (path === '/api/character-creation/explanations/') {
      await route.fulfill({ json: {} });
    } else if (path === '/api/character-creation/drafts/' && method === 'GET') {
      await route.fulfill({ json: [draft] });
    } else if (path === `/api/character-creation/drafts/${DRAFT_ID}/` && method === 'PATCH') {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      Object.assign(draft, body);
      await route.fulfill({ json: draft });
    } else if (path === '/api/character-creation/origin-templates/') {
      await route.fulfill({ json: [draft.selected_origin_template] });
    } else if (path === '/api/character-creation/families/') {
      await route.fulfill({ json: [] });
    } else if (path === '/api/character-creation/vacancies/') {
      await route.fulfill({ json: [] });
    } else if (path === '/api/character-creation/genders/') {
      await route.fulfill({
        json: [
          { id: 1, key: 'male', display_name: 'Male' },
          { id: 2, key: 'female', display_name: 'Female' },
        ],
      });
    } else if (path === '/api/character-creation/house-titles/') {
      await route.fulfill({
        json: [
          {
            id: DUCHY_ID,
            name: DUCHY_NAME,
            tier: 'duchy',
            realm_name: 'Arx',
            seat_domain_name: '',
            templates: [TEMPLATE],
          },
        ],
      });
    } else if (path === `/api/character-creation/drafts/${DRAFT_ID}/house-claim/`) {
      if (method === 'GET') {
        if (houseClaim) {
          await route.fulfill({ json: houseClaim });
        } else {
          await route.fulfill({ status: 404, json: { detail: 'No house claim.' } });
        }
      } else if (method === 'POST') {
        postedPayload = route.request().postDataJSON() as Record<string, unknown>;
        houseClaim = {
          id: 900,
          house_name: postedPayload.house_name,
          title_name: DUCHY_NAME,
          status: 'pending',
          review_note: '',
          words: postedPayload.words,
          colors: postedPayload.colors,
          sigil_description: postedPayload.sigil_description,
          aspects: [],
          kin: postedPayload.kin,
          lands: postedPayload.lands,
          estate_name: (postedPayload.estate as Record<string, unknown>)?.name ?? '',
          estate_description: (postedPayload.estate as Record<string, unknown>)?.description ?? '',
          estate_district_id: null,
          founder_relation: postedPayload.founder_relation,
          founder_is_heir: postedPayload.founder_is_heir,
        };
        await route.fulfill({ status: 201, json: houseClaim });
      }
    } else if (path === '/api/almanach/realms/') {
      await route.fulfill({
        json: {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: REALM_ID,
              name: 'Arx',
              formal_name: '',
              default_tithe_pct: 10,
              unclaimed_by_tier: UNCLAIMED_BY_TIER,
            },
          ],
        },
      });
    } else if (path === `/api/almanach/realms/${REALM_ID}/ladder/`) {
      await route.fulfill({
        json: { rows: LADDER_ROWS, unclaimed_by_tier: UNCLAIMED_BY_TIER },
      });
    } else if (path === `/api/almanach/realms/${REALM_ID}/charter/`) {
      await route.fulfill({ json: CHARTER });
    } else if (path === '/api/almanach/land-shapes/') {
      await route.fulfill({
        json: {
          count: 2,
          next: null,
          previous: null,
          results: [
            { id: 1, name: 'Hills', description: '', sort_order: 0 },
            { id: 2, name: 'Forest', description: '', sort_order: 1 },
          ],
        },
      });
    } else if (path === '/api/almanach/houses/') {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });

  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/characters/create');

  // Lineage stage, claim path: the founder panel is already mounted
  // (`showHouseFounding`), at the Seat step, defaulted to the duchy's own
  // area row.
  await expect(page.getByText('Define a house')).toBeVisible();
  const claimButton = page.getByRole('button', { name: `Claim ${DUCHY_NAME}` });
  await expect(claimButton).toBeVisible();
  await claimButton.click();

  // House chapter (plate F-II): name the house, a few stylings, the backstory.
  await expect(page.getByRole('heading', { name: /^House/ })).toBeVisible();
  await page.locator('#founder-house-name').fill('Ashgrave');
  await page.locator('#founder-house-words').fill('Iron Endures');
  await page.locator('#founder-house-colors').fill('Grey and gold');
  await page.locator('#founder-house-sigil').fill('A grey tower on a gold field.');
  await page.locator('#founder-house-backstory').fill('A frontier house carved from the hills.');
  await page.getByRole('button', { name: 'Next', exact: true }).click();

  // Family chapter (plate F-III): add a spouse to the founder's own node
  // (`founder_relation` defaults to `head`, so the founder herself is the
  // union's other half — `AddKinDialog`'s spouse picker offers her synthetic
  // node, named "Given name" until `CharacterDraft` carries a real one).
  await page.getByRole('button', { name: '⊕ a sibling · a spouse' }).click();
  await page.locator('#add-kin-name').fill('Lady Osrin');
  await page.locator('#add-kin-relation').click();
  await page.getByRole('option', { name: 'spouse', exact: true }).click();
  await page.locator('#add-kin-spouse').click();
  await page.getByRole('option', { name: 'Given name', exact: true }).click();
  await page.getByRole('button', { name: 'Add', exact: true }).click();
  await expect(page.getByText('Lady Osrin')).toBeVisible();
  await page.getByRole('button', { name: 'Next', exact: true }).click();

  // Land chapter (plate F-IV): write the duchy's own description.
  await page.locator('#founder-land-prose').fill('Hill country, hard-won and harder held.');
  await page.getByRole('button', { name: 'Next', exact: true }).click();

  // Estate chapter (plate F-V): name a townhouse in the realm capital.
  await page.locator('#founder-estate-name').fill('Ashgrave House');
  await page.locator('#founder-estate-prose').fill('A narrow house on a quiet street.');
  await page.getByRole('button', { name: 'Next', exact: true }).click();

  // Record chapter (plate F-VI): review and submit.
  await expect(page.getByText('Submit for review')).toBeVisible();
  await page.getByRole('button', { name: 'Submit for review' }).click();

  // The night plate (`SubmittedPlate`, plate F-VI's `.night`).
  await expect(page.getByRole('heading', { name: 'Submitted' })).toBeVisible();
  await expect(page.getByText(`House Ashgrave`)).toBeVisible();
  await expect(page.getByText('pending review')).toBeVisible();

  expect(postedPayload).not.toBeNull();
  const posted = postedPayload as unknown as Record<string, unknown>;
  expect(posted.title).toBe(DUCHY_ID);
  expect(posted.founder_relation).toBe('head');
  expect(Array.isArray(posted.kin)).toBe(true);
  expect((posted.kin as Record<string, unknown>[]).some((k) => k.relation === 'spouse')).toBe(true);
  expect(Array.isArray(posted.lands)).toBe(true);
  expect((posted.lands as Record<string, unknown>[]).length).toBeGreaterThan(0);
  expect(posted.estate).toEqual({
    name: 'Ashgrave House',
    description: 'A narrow house on a quiet street.',
  });

  expect(errors).toEqual([]);
});
