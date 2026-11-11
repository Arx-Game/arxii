import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import { test, expect, type Page } from '@playwright/test';

/**
 * Review evidence for #5080 (slice 4 of #5069): regional events on the production
 * bundle, every `/api/**` call answered by fixtures shaped like the serializers. A duchy
 * page lists the blight over it with Close and opens a famine from the authored kinds;
 * the Atlas tints the struck duchy, its county and its seat over the holder colour and
 * names the event in the legend, while the neighbouring duchy stays as it was.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '5080');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const REALM_ID = 5;
const KINGDOM_ID = 8;
const DUCHY_ID = 20;
const PIROPA_ID = 9;
const VAMPA_AREA = 200;
const INFERNA_COUNTY_AREA = 300;
const PERDITION_AREA = 400;
const SALTREACH_AREA = 220;
const SALTREACH_COUNTY_AREA = 320;
const KINGDOM_AREA = 100;
const BLIGHT_EVENT = 5;

const STAFF_CHARACTER = {
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

const paginated = <T>(results: T[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error' && !/Failed to load resource/.test(msg.text())) {
      errors.push(msg.text());
    }
  });
  page.on('pageerror', (err) => errors.push(String(err)));
  return errors;
}

const books = { income_week: 12400, uncollected: 37200, treasury: 210000, streams: 3 };

const DUCHY_DOC = {
  title: {
    title_id: DUCHY_ID,
    name: 'Vampa',
    tier: 'duchy',
    realm_id: REALM_ID,
    realm: 'Inferna',
    house_id: PIROPA_ID,
    held_by: 'House Piropa',
    holder_id: 11,
    holder: 'Hael Piropa',
    sworn_to: '',
    succession: 'Enatic gifted',
    seat: 'Perdition',
    is_claimable: false,
    chain_top_id: KINGDOM_ID,
    station: 'seated',
    pledged_liege: null,
    area_id: VAMPA_AREA,
  },
  demesne: null,
  holdings: [],
  books,
  forces: [],
  vassals: [
    {
      title_id: 30,
      name: 'Inferna',
      held_by: 'House Piropa',
      demesne: 1,
      vassals: 1,
      population: 37700,
    },
    {
      title_id: 31,
      name: 'Ashfall',
      held_by: 'House Ashen',
      demesne: 1,
      vassals: 0,
      population: 23500,
    },
  ],
  chartered_fiefs: [],
  chartered_by: [],
  claims: [],
  chain: [
    { title_id: null, name: 'Inferna', tier: 'realm' },
    { title_id: KINGDOM_ID, name: 'Inferna', tier: 'kingdom' },
  ],
  events: [
    {
      event_id: BLIGHT_EVENT,
      kind: 'Blight',
      area_id: VAMPA_AREA,
      area: 'Vampa',
      severity_pct: 80,
      started_at: '2026-11-11T06:00:00Z',
    },
  ],
};

const EVENT_KINDS = [
  {
    id: 1,
    name: 'Blight',
    description: 'The crops fail.',
    capacity_cut_pct: 50,
    prosperity_delta: -20,
    unrest_delta: 15,
    crisis_type_id: 3,
  },
  {
    id: 2,
    name: 'Famine',
    description: 'The granaries empty.',
    capacity_cut_pct: 30,
    prosperity_delta: -10,
    unrest_delta: 20,
    crisis_type_id: null,
  },
];

const REGIONAL_EVENTS = [
  {
    id: BLIGHT_EVENT,
    kind: 'Blight',
    kind_id: 1,
    area_id: VAMPA_AREA,
    area: 'Vampa',
    realm_id: REALM_ID,
    severity_pct: 80,
    started_at: '2026-11-11T06:00:00Z',
    ended_at: null,
    note: 'GM only',
  },
];

// --- the map: a 2x2-cell region, land in the middle, two duchies side by side ------
const REGION = {
  id: 1,
  name: 'Catenys',
  area: null,
  area_name: '',
  anchor_x: 0,
  anchor_y: 0,
  width_cells: 2,
  height_cells: 2,
  pips_per_cell: 10,
  created_at: '2026-10-12T00:00:00Z',
  latest_upload: {
    id: 1,
    file_name: 'catenys.map',
    byte_size: 12,
    generator_version: '1.154.0',
    source_width_px: 1200,
    source_height_px: 1200,
    uploaded_by_name: 'staff',
    uploaded_at: '2026-10-12T00:00:00Z',
    rasterized_at: '2026-10-12T00:00:00Z',
  },
};

const isLand = (x: number, y: number) => x >= 3 && x <= 16 && y >= 4 && y <= 15;
const terrainAt = (x: number, y: number): string => {
  if (!isLand(x, y)) return 'water';
  if (y < 8) return 'forest';
  return x > 12 ? 'hill' : 'plain';
};
const PIPS: [number, number, string, boolean][] = [];
for (let y = 0; y < 20; y += 1) {
  for (let x = 0; x < 20; x += 1) {
    const terrain = terrainAt(x, y);
    PIPS.push([x, y, terrain, false]);
  }
}
const box = (x0: number, y0: number, x1: number, y1: number): [number, number][] => {
  const out: [number, number][] = [];
  for (let y = y0; y <= y1; y += 1) for (let x = x0; x <= x1; x += 1) out.push([x, y]);
  return out;
};
const vampaPips = box(3, 4, 9, 15);
const saltreachPips = box(10, 4, 16, 15);
const footprint = (
  areaId: number,
  name: string,
  level: number,
  levelDisplay: string,
  parent: number | null,
  pips: [number, number][],
  extra: Record<string, unknown> = {}
) => ({
  area_id: areaId,
  name,
  level,
  level_display: levelDisplay,
  parent_id: parent,
  realm_id: REALM_ID,
  holder_org_id: PIROPA_ID,
  holder_name: 'House Piropa',
  title_id: null,
  seat: null,
  pips,
  charters: [],
  ...extra,
});
const PIPS_PAYLOAD = {
  region: REGION,
  terrains: ['water', 'plain', 'forest', 'hill'],
  pips: PIPS,
  footprints: [
    footprint(KINGDOM_AREA, 'Inferna', 60, 'Kingdom', null, [...vampaPips, ...saltreachPips], {
      title_id: KINGDOM_ID,
    }),
    footprint(VAMPA_AREA, 'Vampa', 56, 'Duchy', KINGDOM_AREA, vampaPips, { title_id: DUCHY_ID }),
    footprint(INFERNA_COUNTY_AREA, 'Inferna', 53, 'County', VAMPA_AREA, vampaPips, {
      title_id: 30,
      seat: [6, 9],
    }),
    footprint(PERDITION_AREA, 'Perdition', 40, 'Barony', INFERNA_COUNTY_AREA, [[6, 9]], {
      title_id: 40,
      seat: [6, 9],
    }),
    footprint(SALTREACH_AREA, 'Saltreach', 56, 'Duchy', KINGDOM_AREA, saltreachPips, {
      title_id: 22,
      holder_org_id: 13,
      holder_name: 'House Varro',
    }),
    footprint(SALTREACH_COUNTY_AREA, 'Brine', 53, 'County', SALTREACH_AREA, saltreachPips, {
      title_id: 32,
      holder_org_id: 13,
      holder_name: 'House Varro',
      seat: [13, 9],
    }),
  ],
  landless_titles: [],
};

const LADDER_ROW = (
  id: number,
  name: string,
  tier: string,
  level: number,
  parent: number | null,
  extra: Record<string, unknown> = {}
) => ({
  title_id: id,
  name,
  is_defined: true,
  tier,
  level,
  parent_title_id: parent,
  house_id: PIROPA_ID,
  house_name: 'House Piropa',
  state: 'Held',
  is_seat_of: '',
  sworn_to: '',
  demesne: 1,
  vassals: 0,
  population: 1000,
  claimable: false,
  seat_domain_id: 400,
  comes_with: '',
  chain_top_id: KINGDOM_ID,
  claimant_name: '',
  station: 'seated',
  ...extra,
});
const LADDER = {
  rows: [
    LADDER_ROW(KINGDOM_ID, 'Inferna', 'kingdom', 0, null),
    LADDER_ROW(DUCHY_ID, 'Vampa', 'duchy', 1, KINGDOM_ID),
    LADDER_ROW(30, 'Inferna', 'county', 2, DUCHY_ID),
    LADDER_ROW(40, 'Perdition', 'barony', 3, 30),
    LADDER_ROW(22, 'Saltreach', 'duchy', 1, KINGDOM_ID, {
      house_id: 13,
      house_name: 'House Varro',
    }),
    LADDER_ROW(32, 'Brine', 'county', 2, 22, { house_id: 13, house_name: 'House Varro' }),
  ],
  unclaimed_by_tier: {},
};

const HOUSE_DOC = { family: { family_id: 4, nodes: [], parentage: [], unions: [] } };

const dispatches: Array<Record<string, unknown>> = [];
// whether the Atlas walk's realm has its blight open; the before shot has none
let eventsOpen = true;

async function mockApi(page: Page) {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/user/') {
      await route.fulfill({
        json: {
          id: 1,
          username: 'archivist',
          display_name: 'Archivist',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: false,
          is_staff: true,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: 1,
          selected_entry: STAFF_CHARACTER,
        },
      });
      return;
    }
    if (p === '/api/roster/entries/mine/') return route.fulfill({ json: [STAFF_CHARACTER] });
    if (p === '/api/world-builder/areas/grants/')
      return route.fulfill({ json: { is_staff: true, grants: [] } });
    if (p === '/api/world-builder/region-maps/')
      return route.fulfill({ json: [{ id: 1, name: 'Catenys' }] });
    if (p === '/api/world-builder/region-maps/1/pips/')
      return route.fulfill({ json: PIPS_PAYLOAD });
    if (p === `/api/almanach/titles/${DUCHY_ID}/document/`)
      return route.fulfill({ json: DUCHY_DOC });
    if (p === `/api/almanach/houses/${PIROPA_ID}/document/`)
      return route.fulfill({ json: HOUSE_DOC });
    if (p === '/api/almanach/realms/')
      return route.fulfill({ json: paginated([{ id: REALM_ID, name: 'Inferna' }]) });
    if (p === `/api/almanach/realms/${REALM_ID}/ladder/`) return route.fulfill({ json: LADDER });
    if (p === '/api/almanach/houses/')
      return route.fulfill({ json: paginated([{ id: PIROPA_ID, name: 'House Piropa' }]) });
    if (p === '/api/almanach/regional-event-kinds/')
      return route.fulfill({ json: paginated(EVENT_KINDS) });
    if (p === '/api/almanach/regional-events/')
      return route.fulfill({ json: paginated(eventsOpen ? REGIONAL_EVENTS : []) });
    if (p.startsWith('/api/actions/characters/') && p.endsWith('/dispatch/')) {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      dispatches.push(body);
      return route.fulfill({
        json: { backend: 'registry', deferred: false, message: 'ok', data: {}, success: true },
      });
    }
    const arrays = [
      '/api/magic/character-resonances/',
      '/api/precapture-consent-requests/',
      '/api/items/makeover-requests/',
      '/api/gm/summon-offers/',
      '/api/ceremonies/seance-offers/',
      '/api/ceremonies/conversion-offers/',
      '/api/magic/rituals/sessions/',
      '/api/personas/',
      '/api/world-builder/areas/unfiled-rooms/',
    ];
    if (arrays.includes(p)) return route.fulfill({ json: [] });
    if (p === '/api/interactions/') return route.fulfill({ json: { results: [], next: null } });
    return route.fulfill({ json: paginated([]) });
  });
}

/** Zoom to the cap (8): Fit never zooms in, the plus button does, 1.25 a press. */
async function zoomIn(page: Page) {
  const plus = page.getByRole('button', { name: '+', exact: true });
  for (let i = 0; i < 10; i += 1) await plus.click();
}

test.describe('Dominion slice 4 (#5080)', () => {
  test.beforeEach(async ({ page }) => {
    dispatches.length = 0;
    await mockApi(page);
    await page.setViewportSize({ width: 1280, height: 1100 });
  });

  test('1. a duchy page: the blight over it, Close, then Open a famine here', async ({ page }) => {
    const errors = trackErrors(page);
    await page.goto(`/staff/almanach/titles/${DUCHY_ID}`);
    await expect(page.getByRole('heading', { level: 3 })).toContainText('Vampa');
    const events = page
      .getByRole('heading', { name: 'Events' })
      .locator('xpath=following-sibling::*[1]');
    await expect(events.getByRole('strong').filter({ hasText: 'Blight' })).toBeVisible();
    await expect(events.getByText(/over Vampa/)).toBeVisible();
    await expect(events.getByText('80%')).toBeVisible();
    await page.screenshot({ path: shot('1-duchy-events-row.png'), fullPage: true });

    await events.getByRole('button', { name: 'Close' }).click();
    await expect.poll(() => dispatches.length).toBe(1);
    expect(dispatches[0]).toMatchObject({
      ref: { backend: 'registry', registry_key: 'almanach_close_regional_event' },
      kwargs: { event_id: BLIGHT_EVENT },
    });

    await expect(events.getByRole('button', { name: 'Open' })).toBeDisabled();
    await events.getByLabel('event').selectOption({ label: 'Famine' });
    await events.getByLabel('severity').fill('40');
    await page.screenshot({ path: shot('2-duchy-open-famine.png'), fullPage: true });
    await events.getByRole('button', { name: 'Open' }).click();
    await expect.poll(() => dispatches.length).toBe(2);
    expect(dispatches[1]).toMatchObject({
      ref: { backend: 'registry', registry_key: 'almanach_open_regional_event' },
      kwargs: { kind_id: 2, area_id: VAMPA_AREA, severity_pct: 40 },
    });
    expect(errors).toEqual([]);
  });

  test('2. the Atlas: the struck duchy, its county and its seat tinted, named in the legend', async ({
    page,
  }) => {
    const errors = trackErrors(page);
    const viewport = page.getByTestId('region-map-viewport');
    const legend = page.getByTestId('region-map-legend');
    // before: the same map with nothing open over it
    eventsOpen = false;
    await page.goto(`/staff/world-builder/map/1?focus=${VAMPA_AREA}`);
    await expect(page.getByRole('heading', { name: 'Catenys' })).toBeVisible();
    await expect(viewport).toHaveAttribute('data-struck', '0');
    await expect(legend).not.toContainText('Blight');
    await zoomIn(page);
    await expect(viewport).toHaveAttribute('data-zoom', '8.00');
    await page.screenshot({ path: shot('3-atlas-before.png'), fullPage: true });
    // after: the blight over Vampa
    eventsOpen = true;
    await page.reload();
    await expect(legend).toContainText('Blight over Vampa');
    // the duchy, its county and its barony; the kingdom above and Saltreach beside are not
    await expect(viewport).toHaveAttribute('data-struck', '3');
    await zoomIn(page);
    await expect(viewport).toHaveAttribute('data-zoom', '8.00');
    await page.screenshot({ path: shot('3-atlas-blight-over-vampa.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});
