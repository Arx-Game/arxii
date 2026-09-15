import { test, expect, type Page, type Route } from '@playwright/test';
import { mockRestRoutes } from './support/gameHarness';

// #3860: staff reach an unfiled room from the Atlas's index rail, and the
// room document's exit dialog can make a one-way exit. One journey per demo
// screen (issue #3860, demo v1). The builder REST surface is a fixture
// (there is no Django behind the preview build); the rail, the document, the
// dialog, the chips and the toast are the real ones.

const LIMBO_ID = 2;
const SANDBOX_ID = 77;
const CITY_ID = 5;
const CITY_CENTER_ID = 40;

const CATALOGS = {
  species: [],
  resonances: [],
  distinctions: [],
  fame_tiers: [],
  realms: [],
  climates: [],
  societies: [],
  permit_options: [],
  feature_kinds: [],
  npc_roles: [],
  blueprints: [],
  size_tiers: [],
  starting_areas: [],
  beginnings: [],
};

const CITY = {
  id: CITY_ID,
  name: 'Arx',
  slug: 'arx',
  level: 40,
  level_display: 'City',
  origin: 'authored',
  parent: null,
  children_count: 0,
  grid_x: null,
  grid_y: null,
  realm: null,
  climate: null,
  dominant_society: null,
  effective_climate: null,
  art_url: null,
  description: '',
  color: '',
  permit_eligibility: 'none',
};

function room(id: number, name: string, areaId: number | null, fixtureKey: string | null) {
  return {
    id,
    name,
    description: '',
    is_public: true,
    is_social_hub: false,
    is_outdoor: false,
    enclosure: 'walled',
    size_name: null,
    grid_x: null,
    grid_y: null,
    floor: 0,
    fixture_key: fixtureKey,
    origin: 'authored',
    exported_at: null,
    published_at: null,
    needs_prose: false,
    art_url: null,
    stats: [],
    area_id: areaId,
    size_units: null,
    default_blueprint: null,
    places: [],
    feature: null,
    functionaries: [],
    ambient_counts: { lines: 0, emits: 0 },
    travel_hub: null,
    starting_bindings: [],
    occupant_count: 0,
    clues: [],
    clue_triggers: [],
    portal_anchors: [],
    desc_variants: [],
  };
}

interface ExitRow {
  id: number;
  name: string;
  to_room_id: number | null;
  kind: string;
  is_open: boolean;
  aliases: string[];
  one_way: boolean;
}

interface Fixture {
  /** Limbo's outgoing exits; the link journeys push onto it after a dispatch. */
  limboExits: ExitRow[];
  /** Every builder action the page dispatched, as its kwargs. */
  dispatched: Array<{ key: string; kwargs: Record<string, unknown> }>;
}

/** The builder REST surface the atlas reads, over the harness's account fixture. */
async function mockAtlasRoutes(page: Page, options: { staff?: boolean } = {}): Promise<Fixture> {
  const fixture: Fixture = { limboExits: [], dispatched: [] };
  await mockRestRoutes(page, { staff: options.staff ?? true });

  await page.route('**/api/world-builder/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/api/world-builder/areas/') {
      const results = url.searchParams.get('has_parent') === 'false' ? [CITY] : [];
      await route.fulfill({ json: { count: results.length, next: null, previous: null, results } });
    } else if (path === `/api/world-builder/areas/${CITY_ID}/manager/`) {
      await route.fulfill({
        json: {
          area: CITY,
          catalogs: CATALOGS,
          breadcrumb: [],
          rooms: [],
          resonances: [],
          exits: [],
        },
      });
    } else if (path === '/api/world-builder/areas/grants/') {
      await route.fulfill({ json: { is_staff: options.staff ?? true, grants: [] } });
    } else if (path === '/api/world-builder/areas/unfiled-rooms/') {
      await route.fulfill({
        json:
          options.staff === false
            ? []
            : [
                {
                  id: LIMBO_ID,
                  name: 'Limbo',
                  area_id: null,
                  area_name: null,
                  floor: 0,
                  fixture_key: 'limbo',
                },
                {
                  id: SANDBOX_ID,
                  name: 'Sandbox',
                  area_id: null,
                  area_name: null,
                  floor: 0,
                  fixture_key: null,
                },
              ],
      });
    } else if (path === '/api/world-builder/areas/room-detail/') {
      const roomId = Number(url.searchParams.get('room_id'));
      const isLimbo = roomId === LIMBO_ID;
      await route.fulfill({
        json: {
          id: roomId,
          room: isLimbo
            ? room(LIMBO_ID, 'Limbo', null, 'limbo')
            : room(roomId, 'Sandbox', null, null),
          catalogs: CATALOGS,
          breadcrumb: [],
          exits: isLimbo ? fixture.limboExits : [],
          comfort: { level: 0, points: 0, amenity: 0, axes: [] },
          ambient_lines: [],
          ambient_emits: [],
          resonances: [],
          dominant_affinity: null,
        },
      });
    } else if (path === '/api/world-builder/areas/room-search/') {
      const term = (url.searchParams.get('search') ?? '').toLowerCase();
      const hits = 'city center'.startsWith(term)
        ? [
            {
              id: CITY_CENTER_ID,
              name: 'City Center',
              area_id: CITY_ID,
              area_name: 'Arx',
              floor: 0,
              fixture_key: null,
            },
          ]
        : [];
      await route.fulfill({ json: hits });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not found.' } });
    }
  });

  // The staff link action: the fixture answers as the server would, and the
  // detail fixture grows the exit so the invalidated document shows it.
  await page.route('**/api/actions/characters/*/dispatch/', async (route: Route) => {
    const body = route.request().postDataJSON() as {
      ref: { registry_key: string };
      kwargs: Record<string, unknown>;
    };
    fixture.dispatched.push({ key: body.ref.registry_key, kwargs: body.kwargs });
    const oneWay = body.kwargs.one_way === true;
    fixture.limboExits.push({
      id: 900 + fixture.limboExits.length,
      name: String(body.kwargs.name_ab),
      to_room_id: CITY_CENTER_ID,
      kind: 'door',
      is_open: true,
      aliases: [],
      one_way: oneWay,
    });
    await route.fulfill({
      json: {
        backend: 'registry',
        deferred: false,
        success: true,
        message: oneWay
          ? 'Linked Limbo -> City Center (one way).'
          : 'Linked Limbo <-> City Center.',
        data: {},
      },
    });
  });
  return fixture;
}

async function openLimbo(page: Page): Promise<void> {
  await page.goto('/staff/world-builder');
  const unfiled = page.getByTestId('index-unfiled');
  await expect(unfiled).toBeVisible();
  await unfiled.getByTestId('index-unfiled-room').filter({ hasText: 'Limbo' }).click();
  await expect(page.getByTestId('room-document')).toBeVisible();
}

/** Opens the exit dialog and names City Center through its own suggestion. */
async function nameCityCenter(page: Page): Promise<void> {
  await page.getByTestId('add-exit-button').click();
  await page.getByTestId('add-dialog-name').fill('City');
  await page.getByTestId('add-dialog-exit-suggestion').filter({ hasText: 'City Center' }).click();
  await expect(page.getByTestId('add-dialog-name')).toHaveValue('City Center');
}

test.describe('one-way exits and the unfiled rooms (#3860)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
  });

  test('screen 1: Limbo opens from the rail without a search', async ({ page }) => {
    await mockAtlasRoutes(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/staff/world-builder');
    const unfiled = page.getByTestId('index-unfiled');
    await expect(unfiled).toContainText('Unfiled rooms — 2');
    await expect(unfiled.getByTestId('index-unfiled-room')).toHaveText(['Limbo', 'Sandbox']);

    await unfiled.getByTestId('index-unfiled-room').filter({ hasText: 'Limbo' }).click();
    await expect(page.getByTestId('room-document')).toBeVisible();
    await expect(page.getByTestId('room-name-input')).toHaveValue('Limbo');
    await expect(page.getByTestId('compass-no-area-note')).toHaveText(
      'this room has no area to place it within'
    );
    await expect(page.getByTestId('exit-chips')).toBeEmpty();
    await page.screenshot({ path: '../docs/reviews/3860/screen-1-unfiled-1280.png' });
    expect(errors).toEqual([]);
  });

  test('screens 2 and 3: Both ways is the default, One way hides the way back', async ({
    page,
  }) => {
    await mockAtlasRoutes(page);
    await openLimbo(page);
    await nameCityCenter(page);

    // Screen 2: the direction pair sits after Leads to, Both ways pressed.
    await expect(page.getByTestId('add-dialog-both-ways')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('add-dialog-one-way')).toHaveAttribute('aria-pressed', 'false');
    await expect(page.getByTestId('add-dialog-exit-back')).toBeVisible();
    await expect(page.getByTestId('add-dialog-exit-note')).toHaveText(
      'links to City Center, and City Center back to here'
    );
    await page.screenshot({ path: '../docs/reviews/3860/screen-2-both-ways-1280.png' });

    // Screen 3: One way drops Exit back and the note says nothing leads back.
    await page.getByTestId('add-dialog-one-way').click();
    await expect(page.getByTestId('add-dialog-one-way')).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByTestId('add-dialog-exit-back')).toHaveCount(0);
    await expect(page.getByTestId('add-dialog-exit-note')).toHaveText(
      'links to City Center; nothing leads back to here'
    );
    await page.screenshot({ path: '../docs/reviews/3860/screen-3-one-way-1280.png' });

    // Both ways brings Exit back straight back.
    await page.getByTestId('add-dialog-both-ways').click();
    await expect(page.getByTestId('add-dialog-exit-back')).toBeVisible();
  });

  test('screen 4: a one-way link sends no return name and the chip says so', async ({ page }) => {
    const fixture = await mockAtlasRoutes(page);
    await openLimbo(page);
    await nameCityCenter(page);
    await page.getByTestId('add-dialog-one-way').click();
    await page.getByTestId('add-dialog-exit-there').fill('down');
    await page.getByTestId('add-dialog-submit').click();

    await expect.poll(() => fixture.dispatched.length).toBe(1);
    expect(fixture.dispatched[0]).toEqual({
      key: 'staff_link_rooms',
      kwargs: { room_a_id: LIMBO_ID, room_b_id: CITY_CENTER_ID, name_ab: 'down', one_way: true },
    });
    await expect(page.getByText('Linked Limbo -> City Center (one way).')).toBeVisible();
    const chip = page.getByTestId('exit-chip-900');
    await expect(chip).toContainText('down');
    await expect(chip.getByTestId('exit-chip-one-way')).toHaveText('one way');
    await expect(page.getByTestId('add-dialog-submit')).toHaveCount(0);
    await page.screenshot({ path: '../docs/reviews/3860/screen-4-linked-one-way-1280.png' });
  });

  test('screen 5: a two-way link is unchanged', async ({ page }) => {
    const fixture = await mockAtlasRoutes(page);
    await openLimbo(page);
    await nameCityCenter(page);
    await page.getByTestId('add-dialog-exit-there').fill('down');
    await page.getByTestId('add-dialog-exit-back').fill('up');
    await page.getByTestId('add-dialog-submit').click();

    await expect.poll(() => fixture.dispatched.length).toBe(1);
    expect(fixture.dispatched[0]).toEqual({
      key: 'staff_link_rooms',
      kwargs: { room_a_id: LIMBO_ID, room_b_id: CITY_CENTER_ID, name_ab: 'down', name_ba: 'up' },
    });
    await expect(page.getByText('Linked Limbo <-> City Center.')).toBeVisible();
    const chip = page.getByTestId('exit-chip-900');
    await expect(chip).toContainText('down');
    await expect(chip.getByTestId('exit-chip-one-way')).toHaveCount(0);
    await expect(page.getByTestId('add-dialog-submit')).toHaveCount(0);
    await page.screenshot({ path: '../docs/reviews/3860/screen-5-linked-both-ways-1280.png' });
  });

  test('the rail lists no unfiled rooms for a non-staff reader', async ({ page }) => {
    await mockAtlasRoutes(page, { staff: false });
    await page.goto('/staff/world-builder');
    // StaffRoute sends a non-staff account home; the section never renders.
    await expect(page.getByTestId('index-unfiled')).toHaveCount(0);
  });
});
