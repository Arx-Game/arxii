import { test, expect, type Page, type Route } from '@playwright/test';
import { mockRestRoutes } from './support/gameHarness';

// #4242: the Atlas's region-map view. Staff open a region from the index rail's
// Maps section, see the pips and the footprints coloured by holder, carve a
// county's footprint from the realm ladder, and paint a pip's terrain. The
// builder, Almanach and action REST surfaces are fixtures (no Django behind the
// preview build); the rail, the page, the canvas and the dispatches are real.

const REGION_ID = 3;
const REALM_ID = 1;
const COUNTY_TITLE_ID = 100;
const COUNTY_AREA_ID = 10;
const BARONY_AREA_ID = 11;

const CITY = {
  id: 5,
  name: 'Arx',
  slug: 'arx',
  level: 40,
  level_display: 'Barony',
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

const REGION = {
  id: REGION_ID,
  name: 'Catenys',
  area: null,
  area_name: '',
  anchor_x: 0,
  anchor_y: 0,
  width_cells: 4,
  height_cells: 3,
  pips_per_cell: 10,
  created_at: '2026-10-12T00:00:00Z',
  latest_upload: {
    id: 1,
    file_name: 'C1.map',
    byte_size: 12365209,
    generator_version: '1.154.0',
    source_width_px: 1200,
    source_height_px: 1200,
    uploaded_by_name: 'ApostateCD',
    uploaded_at: '2026-10-12T00:00:00Z',
    rasterized_at: '2026-10-12T00:00:00Z',
  },
};

/** A 40 by 30 pip region: sea on the west, a river down column 14, hills then mountains east. */
function pips(): [number, number, string, boolean][] {
  const rows: [number, number, string, boolean][] = [];
  for (let y = 0; y < 30; y += 1) {
    for (let x = 0; x < 40; x += 1) {
      let terrain = 'plain';
      if (x < 6 + Math.round(Math.sin(y / 3) * 2)) terrain = 'water';
      else if (x > 33) terrain = 'mountain';
      else if (x > 28) terrain = 'hill';
      else if (y > 20 && x < 20) terrain = 'forest';
      else if (y < 4) terrain = 'tundra';
      if (x === 20 && y === 10) terrain = 'lake';
      rows.push([x, y, terrain, x === 14 && terrain !== 'water']);
    }
  }
  return rows;
}

const COUNTY_PIPS: [number, number][] = [];
for (let y = 8; y < 14; y += 1) for (let x = 9 + (y % 2); x < 19; x += 1) COUNTY_PIPS.push([x, y]);

const FOOTPRINTS = [
  {
    area_id: COUNTY_AREA_ID,
    name: 'Salvation',
    level: 53,
    level_display: 'County',
    parent_id: null,
    realm_id: REALM_ID,
    holder_org_id: 4,
    holder_name: 'House Stellaris',
    title_id: COUNTY_TITLE_ID,
    seat: [12, 10],
    pips: COUNTY_PIPS,
  },
  {
    area_id: BARONY_AREA_ID,
    name: 'Absolution',
    level: 40,
    level_display: 'Barony',
    parent_id: COUNTY_AREA_ID,
    realm_id: REALM_ID,
    holder_org_id: 4,
    holder_name: 'House Stellaris',
    title_id: 101,
    seat: [12, 10],
    pips: [[12, 10]],
  },
];

interface Fixture {
  dispatched: Array<{ key: string; kwargs: Record<string, unknown> }>;
}

async function mockMapRoutes(page: Page): Promise<Fixture> {
  const fixture: Fixture = { dispatched: [] };
  await mockRestRoutes(page, { staff: true });

  await page.route('**/api/world-builder/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === '/api/world-builder/areas/') {
      const results = url.searchParams.get('has_parent') === 'false' ? [CITY] : [];
      await route.fulfill({ json: { count: results.length, next: null, previous: null, results } });
    } else if (path === `/api/world-builder/areas/${CITY.id}/manager/`) {
      await route.fulfill({
        json: { area: CITY, catalogs: {}, breadcrumb: [], rooms: [], resonances: [], exits: [] },
      });
    } else if (path === '/api/world-builder/areas/grants/') {
      await route.fulfill({ json: { is_staff: true, grants: [] } });
    } else if (path === '/api/world-builder/areas/unfiled-rooms/') {
      await route.fulfill({ json: [] });
    } else if (path === '/api/world-builder/region-maps/') {
      await route.fulfill({ json: [REGION] });
    } else if (path === `/api/world-builder/region-maps/${REGION_ID}/pips/`) {
      await route.fulfill({
        json: {
          region: REGION,
          terrains: [
            'water',
            'lake',
            'plain',
            'forest',
            'hill',
            'mountain',
            'marsh',
            'desert',
            'tundra',
            'glacier',
          ],
          pips: pips(),
          footprints: FOOTPRINTS,
        },
      });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not found.' } });
    }
  });

  await page.route('**/api/almanach/**', async (route: Route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/almanach/realms/') {
      await route.fulfill({
        json: {
          count: 1,
          next: null,
          previous: null,
          results: [{ id: REALM_ID, name: 'Luxen', slug: 'luxen' }],
        },
      });
    } else if (path === `/api/almanach/realms/${REALM_ID}/ladder/`) {
      await route.fulfill({
        json: {
          rows: [
            {
              title_id: COUNTY_TITLE_ID,
              name: 'Salvation',
              is_defined: true,
              tier: 'county',
              level: 53,
              parent_title_id: null,
              house_id: 4,
              house_name: 'House Stellaris',
              state: 'standing',
              is_seat_of: '',
              sworn_to: '',
              demesne: 1,
              vassals: 0,
              claimable: false,
              seat_domain_id: BARONY_AREA_ID,
              comes_with: '',
              chain_top_id: COUNTY_TITLE_ID,
              claimant_name: '',
            },
          ],
          unclaimed_by_tier: {},
        },
      });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not found.' } });
    }
  });

  await page.route('**/api/actions/characters/*/dispatch/', async (route: Route) => {
    const body = route.request().postDataJSON() as {
      ref: { registry_key: string };
      kwargs: Record<string, unknown>;
    };
    fixture.dispatched.push({ key: body.ref.registry_key, kwargs: body.kwargs });
    await route.fulfill({ json: { success: true, message: 'Done.', data: { added: 3 } } });
  });
  return fixture;
}

async function openRegion(page: Page): Promise<void> {
  await page.goto('/staff/world-builder');
  await page
    .getByTestId('index-maps')
    .getByRole('button', { name: /Catenys/ })
    .click();
  await expect(page.getByTestId('region-map-page')).toBeVisible();
  await expect(page.getByTestId('region-map-canvas')).toHaveAttribute('width', '240');
}

/** Drag across pips in canvas coordinates at zoom 1 (6 px a pip), from the canvas's top-left. */
async function dragPips(page: Page, from: [number, number], to: [number, number]) {
  const box = await page.getByTestId('region-map-canvas').boundingBox();
  if (!box) throw new Error('no canvas');
  const px = (pip: number) => box.x + pip * 6 + 3;
  const py = (pip: number) => box.y + pip * 6 + 3;
  await page.mouse.move(px(from[0]), py(from[1]));
  await page.mouse.down();
  await page.mouse.move(px(to[0]), py(to[1]), { steps: 6 });
  await page.mouse.up();
}

test('the Maps rail opens a region; a click on a footprint opens its panel', async ({ page }) => {
  await mockMapRoutes(page);
  await openRegion(page);
  await expect(page.getByRole('heading', { name: 'Catenys' })).toBeVisible();
  await expect(page.getByText(/4 × 3 cells · 400 miles across · C1.map/)).toBeVisible();
  await page.screenshot({ path: 'e2e/evidence/atlas-region-map-4242/open.png', fullPage: true });
  // the panel starts on open ground, and a click on the county opens it
  await expect(page.getByTestId('region-map-panel')).toContainText('Open ground');
  const box = await page.getByTestId('region-map-canvas').boundingBox();
  if (!box) throw new Error('no canvas');
  await page.mouse.click(box.x + 10 * 6 + 3, box.y + 9 * 6 + 3);
  await expect(page.getByRole('heading', { name: 'Salvation' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open in the Almanach' })).toHaveAttribute(
    'href',
    `/staff/almanach/titles/${COUNTY_TITLE_ID}`
  );
  // the barony inside it wins the pip it stands on
  await page.mouse.click(box.x + 12 * 6 + 3, box.y + 10 * 6 + 3);
  await expect(page.getByRole('heading', { name: 'Absolution' })).toBeVisible();
  await page.screenshot({ path: 'e2e/evidence/atlas-region-map-4242/select.png', fullPage: true });
});

test('carve drags pips into a rung picked from the realm ladder', async ({ page }) => {
  const fixture = await mockMapRoutes(page);
  await openRegion(page);
  await page.getByRole('button', { name: 'Carve' }).click();
  await page.getByTestId('carve-realm').selectOption(String(REALM_ID));
  await page.getByTestId('carve-domain').selectOption(String(COUNTY_TITLE_ID));
  await dragPips(page, [20, 9], [22, 9]);
  await expect.poll(() => fixture.dispatched.length).toBe(1);
  expect(fixture.dispatched[0].key).toBe('atlas_carve_footprint');
  expect(fixture.dispatched[0].kwargs.title_id).toBe(COUNTY_TITLE_ID);
  const added = fixture.dispatched[0].kwargs.add as [number, number][];
  expect(added).toContainEqual([20, 9]);
  expect(added).toContainEqual([22, 9]);
  await page.screenshot({ path: 'e2e/evidence/atlas-region-map-4242/carve.png', fullPage: true });
  // shift-drag takes pips out
  await page.keyboard.down('Shift');
  await dragPips(page, [9, 12], [9, 12]);
  await page.keyboard.up('Shift');
  await expect.poll(() => fixture.dispatched.length).toBe(2);
  expect(fixture.dispatched[1].kwargs.remove).toEqual([[9, 12]]);
});

test('paint drags pips to a terrain', async ({ page }) => {
  const fixture = await mockMapRoutes(page);
  await openRegion(page);
  await page.getByRole('button', { name: 'Paint' }).click();
  await page.getByTestId('paint-terrain').selectOption('marsh');
  await dragPips(page, [25, 25], [27, 25]);
  await expect.poll(() => fixture.dispatched.length).toBe(1);
  expect(fixture.dispatched[0].key).toBe('atlas_paint_terrain');
  expect(fixture.dispatched[0].kwargs).toMatchObject({ region_id: REGION_ID, terrain: 'marsh' });
  await page.screenshot({ path: 'e2e/evidence/atlas-region-map-4242/paint.png', fullPage: true });
});
