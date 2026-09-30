import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page, type Route } from '@playwright/test';
import { mockRestRoutes } from '../support/gameHarness';

/**
 * Review evidence for #4084: an unplaced child area is placed on its parent's map by
 * naming it on a planned square. The real Atlas at `/staff/world-builder` on the
 * production bundle; the builder REST surface and the action dispatch are fixtures
 * (there is no Django behind the preview build). The dispatch fixture answers as the
 * server would and records the square, and the children fixture then carries the
 * position, so the invalidated map shows the tile the way it does live.
 */
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');
const EVIDENCE_DIR = path.join(REPO_ROOT, 'docs', 'reviews', '4084');
const shot = (name: string) => path.join(EVIDENCE_DIR, name);

const CITY_ID = 5;
const MARKET_ID = 8;
const DOCKSIDE_ID = 9;

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

function area(
  id: number,
  name: string,
  level: number,
  levelDisplay: string,
  parent: number | null,
  gridX: number | null,
  gridY: number | null
) {
  return {
    id,
    name,
    slug: name.toLowerCase().replace(/\s+/g, '-'),
    level,
    level_display: levelDisplay,
    origin: 'authored',
    parent,
    children_count: 0,
    grid_x: gridX,
    grid_y: gridY,
    realm: null,
    climate: null,
    dominant_society: null,
    effective_climate: null,
    art_url: null,
    description: '',
    color: '',
    permit_eligibility: 'none',
  };
}

const CITY = area(CITY_ID, 'Arx', 40, 'Barony', null, null, null);

interface Fixture {
  children: ReturnType<typeof area>[];
  dispatched: Array<{ key: string; kwargs: Record<string, unknown> }>;
}

async function mockAtlas(page: Page): Promise<Fixture> {
  const fixture: Fixture = {
    // Two placeholder neighborhoods under Arx, as on production: one placed, one not.
    children: [
      area(MARKET_ID, 'Capital Market District', 20, 'Neighborhood', CITY_ID, 0, 0),
      area(DOCKSIDE_ID, 'Dockside Warrens', 20, 'Neighborhood', CITY_ID, null, null),
    ],
    dispatched: [],
  };
  await mockRestRoutes(page, { staff: true });

  await page.route('**/api/world-builder/**', async (route: Route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    if (p === '/api/world-builder/areas/') {
      let results: ReturnType<typeof area>[] = [];
      if (url.searchParams.get('has_parent') === 'false') results = [CITY];
      else if (url.searchParams.get('parent') === String(CITY_ID)) results = fixture.children;
      await route.fulfill({ json: { count: results.length, next: null, previous: null, results } });
    } else if (p === `/api/world-builder/areas/${CITY_ID}/manager/`) {
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
    } else if (p === '/api/world-builder/areas/grants/') {
      await route.fulfill({ json: { is_staff: true, grants: [] } });
    } else if (p === '/api/world-builder/areas/unfiled-rooms/') {
      await route.fulfill({ json: [] });
    } else if (p === '/api/world-builder/areas/room-search/') {
      await route.fulfill({ json: [] });
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
    if (body.ref.registry_key === 'edit_area') {
      const target = fixture.children.find((child) => child.id === body.kwargs.area_id);
      if (target) {
        target.grid_x = Number(body.kwargs.grid_x);
        target.grid_y = Number(body.kwargs.grid_y);
      }
    }
    await route.fulfill({
      json: {
        backend: 'registry',
        deferred: false,
        success: true,
        message: 'Dockside Warrens updated.',
        data: {},
      },
    });
  });
  return fixture;
}

test.describe('placing an unplaced child area on the map (#4084)', () => {
  test('the ledger lists it, naming it on a planned square places it, the tile appears', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    const fixture = await mockAtlas(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));

    await page.goto('/staff/world-builder');
    const ledger = page.getByTestId('area-ledger');
    await expect(ledger).toContainText('Dockside Warrens');
    await expect(page.getByTestId(`lattice-tile-${MARKET_ID}`)).toBeVisible();
    await expect(page.getByTestId(`lattice-tile-${DOCKSIDE_ID}`)).toHaveCount(0);
    await page.screenshot({ path: shot('atlas-before-1280.png'), fullPage: true });

    // Plan the square east of the market, then name the unplaced neighborhood on it.
    const cell = page.getByTestId('lattice-cell-1-0');
    await cell.click();
    await cell.click();
    const nameField = page.getByTestId('add-dialog-name');
    await expect(nameField).toBeVisible();
    await nameField.fill('dock');
    const suggestion = page.getByTestId('add-dialog-place-area-suggestion');
    await expect(suggestion).toHaveText('⌖ place Dockside Warrens (neighborhood) here');
    await suggestion.click();
    await expect(nameField).toHaveValue('Dockside Warrens');
    await expect(page.getByTestId('add-dialog-place-area-note')).toContainText(
      'already exists here as a neighborhood without a place on the map'
    );
    await expect(page.getByTestId('add-dialog-becomes-row')).toHaveCount(0);
    await expect(page.getByLabel('Neighborhood name')).toBeVisible();
    await expect(page.getByTestId('add-dialog-submit')).toHaveText('Place');
    await page.screenshot({ path: shot('atlas-dialog-1280.png'), fullPage: true });

    await page.getByTestId('add-dialog-submit').click();
    await expect(page.getByTestId(`lattice-tile-${DOCKSIDE_ID}`)).toBeVisible();
    expect(fixture.dispatched).toEqual([
      { key: 'edit_area', kwargs: { area_id: DOCKSIDE_ID, grid_x: 1, grid_y: 0 } },
    ]);
    await page.screenshot({ path: shot('atlas-after-1280.png'), fullPage: true });
    expect(errors).toEqual([]);
  });
});
