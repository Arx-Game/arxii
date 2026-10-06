import { expect, test } from '@playwright/test';
import { mockRestRoutes, reachReadySession, CHARACTER, NYX } from './support/gameHarness';

function registryRef(registryKey: string) {
  return {
    backend: 'registry',
    challenge_instance_id: null,
    approach_id: null,
    technique_id: null,
    registry_key: registryKey,
    clash_id: null,
    clash_action_slot: null,
    action_slot: null,
    position_id: null,
    blueprint_id: null,
    application_id: null,
    target_object_id: null,
  };
}

const OWNER_PERSONA_ID = 55;
const ITEM_ID = 44;
const WARDROBE_WORN_ITEM_ID = 45;
const MENU = {
  actor_id: CHARACTER.character_id,
  target: { kind: 'items', target_id: ITEM_ID, owner_persona_id: OWNER_PERSONA_ID },
  label: 'Silver brooch',
  groups: [{ key: 'perception', label: 'Perception' }],
  entries: [
    {
      key: 'look_at_item',
      label: 'Look',
      group: 'perception',
      ref: registryRef('look_at_item'),
      kwargs: {
        menu_target: { kind: 'items', target_id: ITEM_ID, owner_persona_id: OWNER_PERSONA_ID },
      },
      available: true,
      reasons: [],
      inputs: [],
      candidates: [],
      next_candidate_cursor: null,
      action: null,
      risk: null,
    },
  ],
};

function itemActionInputs(key: string) {
  if (key === 'give') {
    return [
      {
        name: 'recipient_persona_id',
        kind: 'recipient',
        required: true,
        target_kind: null,
        default: null,
      },
    ];
  }
  if (key === 'put_in') {
    return [
      {
        name: 'container_item_id',
        kind: 'container',
        required: true,
        target_kind: null,
        default: null,
      },
    ];
  }
  return [];
}

function itemActionCandidates(key: string) {
  if (key === 'give') {
    return [
      {
        key: '77',
        label: 'Visible recipient',
        kwargs: { recipient_persona_id: 77 },
        available: true,
        reasons: [],
      },
    ];
  }
  if (key === 'put_in') {
    return [
      {
        key: '90',
        label: 'Open wicker basket',
        kwargs: { container_item_id: 90 },
        available: true,
        reasons: [],
      },
    ];
  }
  return [];
}

const INVENTORY_ITEM_MENU = {
  actor_id: CHARACTER.character_id,
  target: { kind: 'items', target_id: ITEM_ID },
  label: 'Silver brooch',
  groups: [
    { key: 'perception', label: 'Perception' },
    { key: 'items', label: 'Item handling' },
  ],
  entries: [
    {
      ...MENU.entries[0],
      kwargs: { menu_target: { kind: 'items', target_id: ITEM_ID } },
    },
    ...[
      ['equip', 'Equip'],
      ['give', 'Give'],
      ['put_in', 'Put in'],
      ['drop', 'Drop'],
    ].map(([key, label]) => ({
      key,
      label,
      group: 'items',
      ref: registryRef(key),
      kwargs: { menu_target: { kind: 'items', target_id: ITEM_ID } },
      available: true,
      reasons: [],
      inputs: itemActionInputs(key),
      candidates: itemActionCandidates(key),
      action: null,
      next_candidate_cursor: null,
      risk: null,
    })),
  ],
};

const WARDROBE_WORN_MENU = {
  ...INVENTORY_ITEM_MENU,
  target: { kind: 'items', target_id: WARDROBE_WORN_ITEM_ID },
  label: 'Plain cloak',
  entries: [
    {
      ...MENU.entries[0],
      kwargs: { menu_target: { kind: 'items', target_id: WARDROBE_WORN_ITEM_ID } },
    },
    ...[
      ['unequip', 'Unequip'],
      ['give', 'Give'],
      ['put_in', 'Put in'],
      ['drop', 'Drop'],
    ].map(([key, label]) => ({
      key,
      label,
      group: 'items',
      ref: registryRef(key),
      kwargs: { menu_target: { kind: 'items', target_id: WARDROBE_WORN_ITEM_ID } },
      available: true,
      reasons: [],
      inputs: itemActionInputs(key),
      candidates: itemActionCandidates(key),
      action: null,
      next_candidate_cursor: null,
      risk: null,
    })),
  ],
};

async function readyWithVisibleWornItem(page: import('@playwright/test').Page) {
  await mockRestRoutes(page);
  await page.route('**/api/items/visible-worn/**', async (route) => {
    await route.fulfill({
      json: [
        {
          id: ITEM_ID,
          display_name: 'Silver brooch',
          body_region: 'neck',
          equipment_layer: 'accessory',
          owner_persona_id: OWNER_PERSONA_ID,
        },
      ],
    });
  });
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/items/${ITEM_ID}/menu/**`,
    async (route) => {
      await route.fulfill({ json: MENU });
    }
  );
  await page.route('**/api/items/visible-item-detail/**', async (route) => {
    await route.fulfill({
      json: {
        id: ITEM_ID,
        game_object_id: 401,
        template: {
          id: 12,
          name: 'Silver brooch',
          description: 'A small polished brooch.',
          is_container: false,
        },
        quality_tier: { name: 'Fine', color_hex: '#888888' },
        suggested_value: 0,
        display_name: 'Silver brooch',
        display_description: 'A small polished brooch.',
        display_image_url: null,
        is_usable: false,
        contained_in: null,
        quantity: 1,
        charges: 0,
        is_open: false,
        access_policy: 'open',
        is_currency_instrument: false,
        can_steal: false,
        crafted_provenance: null,
        accents: [],
        silhouette: null,
      },
    });
  });
  const [connection] = await reachReadySession(page);
  return connection;
}

const OBJECT_ID = 301;
const EXIT_ID = 302;
const PLACE_ID = 303;
const ROOM_TARGET_MENU = (kind: 'objects' | 'exits', id: number, label: string) => ({
  actor_id: CHARACTER.character_id,
  target: { kind, target_id: id },
  label,
  groups: [{ key: 'perception', label: 'Perception' }],
  entries: [
    {
      key: 'look',
      label: 'Look',
      group: 'perception',
      ref: registryRef('look'),
      kwargs: { menu_target: { kind, target_id: id } },
      available: true,
      reasons: [],
      inputs: [],
      candidates: [],
      next_candidate_cursor: null,
      action: null,
      risk: null,
    },
  ],
});

async function readyWithRoomTargets(page: import('@playwright/test').Page) {
  await page.setViewportSize({ width: 1280, height: 1200 });
  await mockRestRoutes(page);
  await page.route('**/api/user/', async (route) => {
    await route.fulfill({
      json: {
        id: 1,
        username: 'test-player',
        display_name: 'Test player',
        email: '',
        email_verified: true,
        last_login: null,
        can_create_characters: false,
        is_staff: false,
        is_gm: false,
        available_characters: [{ ...CHARACTER, id: CHARACTER.character_id }],
        pending_applications: [],
        selected_entry_id: CHARACTER.id,
        selected_entry: CHARACTER,
      },
    });
  });
  const ready = reachReadySession(page);
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/objects/${OBJECT_ID}/menu/**`,
    async (route) => {
      await route.fulfill({ json: ROOM_TARGET_MENU('objects', OBJECT_ID, 'Oak chest') });
    }
  );
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/exits/${EXIT_ID}/menu/**`,
    async (route) => {
      await route.fulfill({ json: ROOM_TARGET_MENU('exits', EXIT_ID, 'North gate') });
    }
  );
  await page.route('**/api/actions/characters/18/dispatch/', async (route) => {
    await route.fulfill({
      json: { backend: 'registry', deferred: false, success: true, message: 'A sturdy oak chest.' },
    });
  });
  await page.route('**/api/places/?room=*', async (route) => {
    await route.fulfill({
      json: {
        results: [
          {
            id: PLACE_ID,
            name: 'Window table',
            description: 'A quiet table.',
            viewer_is_present: false,
          },
        ],
      },
    });
  });
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/places/${PLACE_ID}/menu/**`,
    async (route) => {
      await route.fulfill({
        json: {
          actor_id: CHARACTER.character_id,
          target: { kind: 'places', target_id: PLACE_ID },
          label: 'Window table',
          groups: [{ key: 'movement', label: 'Place' }],
          entries: [
            {
              key: 'join_place',
              label: 'Join',
              group: 'movement',
              ref: registryRef('join_place'),
              kwargs: { menu_target: { kind: 'places', target_id: PLACE_ID } },
              available: true,
              reasons: [],
              inputs: [],
              candidates: [],
              action: null,
              risk: null,
            },
          ],
        },
      });
    }
  );
  await page.route(`**/api/places/${PLACE_ID}/join/`, async (route) => {
    await route.fulfill({ status: 200, json: {} });
  });
  const [connection] = await ready;
  connection.route.send(
    JSON.stringify([
      'room_state',
      [],
      {
        room: { dbref: '#2', name: 'Quiet courtyard', description: 'Rain rests on the stones.' },
        characters: [
          { ...NYX, persona_id: 99 },
          { dbref: '#51', name: 'Silver brooch', thumbnail_url: null },
        ],
        objects: [{ dbref: `#${OBJECT_ID}`, name: 'Oak chest', thumbnail_url: null }],
        exits: [{ dbref: `#${EXIT_ID}`, name: 'North gate', thumbnail_url: null }],
        scene: {
          id: 1,
          name: 'Evening in the courtyard',
          description: '',
          is_owner: false,
          has_unseen_observer: false,
        },
      },
    ])
  );
  await expect(page.getByRole('button', { name: /Oak chest/i })).toBeVisible();
  return connection;
}

test.describe('target menus in the room (#4032)', () => {
  test('room object menu preserves the ordinary examine click', async ({ page }) => {
    await readyWithRoomTargets(page);
    const objectRow = page.getByRole('button', { name: /Oak chest/i });
    const request = page.waitForRequest((r) => r.url().includes(`/objects/${OBJECT_ID}/menu/`));
    await objectRow.click({ button: 'right' });
    await request;
    await expect(page.getByTestId('target-menu-label')).toContainText('Oak chest');
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-room-object.png', fullPage: false });
    await page.keyboard.press('Escape');
    await objectRow.click();
    await expect(page.getByTestId(`examine-text-#${OBJECT_ID}`)).toContainText(
      'A sturdy oak chest.'
    );
  });

  test('touch long-press opens the target menu', async ({ page }) => {
    await readyWithRoomTargets(page);
    await page.setViewportSize({ width: 390, height: 844 });
    const placeRow = page.getByRole('button', { name: 'Window table' });
    await placeRow.dispatchEvent('pointerdown', {
      pointerId: 1,
      pointerType: 'touch',
      button: 0,
      isPrimary: true,
    });
    await expect(page.getByRole('menuitem', { name: 'Join' })).toBeVisible({ timeout: 2_000 });
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-place-mobile-touch.png',
      fullPage: false,
    });
  });

  test('target menu remains legible in the dark theme', async ({ page }) => {
    await readyWithRoomTargets(page);
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    const objectRow = page.getByRole('button', { name: /Oak chest/i });
    await objectRow.click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect(page.getByTestId('target-menu-label')).toContainText('Oak chest');
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-room-object-dark.png',
      fullPage: false,
    });
  });

  test('registry menu entries dispatch their registry ref', async ({ page }) => {
    await readyWithRoomTargets(page);
    let dispatchedBody: { ref: { backend: string; registry_key?: string }; kwargs: object } | null =
      null;
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
      async (route) => {
        dispatchedBody = route.request().postDataJSON();
        await route.fulfill({
          json: {
            backend: 'registry',
            deferred: false,
            success: true,
            message: 'You look at the chest.',
          },
        });
      }
    );
    const objectRow = page.getByRole('button', { name: /Oak chest/i });
    await objectRow.click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    const dispatch = page.waitForRequest(
      (request) =>
        request.url().includes(`/api/actions/characters/${CHARACTER.character_id}/dispatch/`) &&
        request.method() === 'POST'
    );
    await page.getByRole('menuitem', { name: 'Look' }).click();
    await dispatch;
    await expect
      .poll(() => dispatchedBody)
      .toEqual({
        ref: registryRef('look'),
        kwargs: { menu_target: { kind: 'objects', target_id: OBJECT_ID } },
      });
  });

  test('open menu stays stable through expiry and room-state invalidation, then refreshes on reopen', async ({
    page,
  }) => {
    const connection = await readyWithRoomTargets(page);
    let menuReads = 0;
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/objects/${OBJECT_ID}/menu/**`,
      async (route) => {
        menuReads += 1;
        await route.fulfill({ json: ROOM_TARGET_MENU('objects', OBJECT_ID, 'Oak chest') });
      }
    );
    await page.clock.install();
    const objectRow = page.getByRole('button', { name: /Oak chest/i });
    await objectRow.click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect.poll(() => menuReads).toBe(1);

    await page.clock.fastForward(31_000);
    for (let index = 0; index < 3; index += 1) {
      connection.route.send(
        JSON.stringify([
          'room_state',
          [],
          {
            room: {
              dbref: '#2',
              name: 'Quiet courtyard',
              description: 'Rain rests on the stones.',
            },
            characters: [
              { ...NYX, persona_id: 99 },
              { dbref: '#51', name: 'Silver brooch', thumbnail_url: null },
            ],
            objects: [{ dbref: `#${OBJECT_ID}`, name: 'Oak chest', thumbnail_url: null }],
            exits: [{ dbref: `#${EXIT_ID}`, name: 'North gate', thumbnail_url: null }],
            scene: {
              id: 1,
              name: 'Evening in the courtyard',
              description: '',
              is_owner: false,
              has_unseen_observer: false,
            },
          },
        ])
      );
    }
    await expect(page.getByTestId('target-menu-label')).toContainText('Oak chest');
    expect(menuReads).toBe(1);
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-cache-open-snapshot.png',
      fullPage: false,
    });

    await page.keyboard.press('Escape');
    await objectRow.click({ button: 'right' });
    await expect.poll(() => menuReads).toBe(2);
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
  });

  test('exit menu preserves the ordinary travel click', async ({ page }) => {
    await readyWithRoomTargets(page);
    const exit = page.getByRole('button', { name: 'North gate' });
    const request = page.waitForRequest((r) => r.url().includes(`/exits/${EXIT_ID}/menu/`));
    await exit.click({ button: 'right' });
    await request;
    await expect(page.getByTestId('target-menu-label')).toContainText('North gate');
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-exit.png', fullPage: false });
    await page.keyboard.press('Escape');
    await exit.click();
  });

  test('place menu offers Join and preserves the existing Join click', async ({ page }) => {
    await readyWithRoomTargets(page);
    const place = page.getByRole('button', { name: 'Window table' });
    const request = page.waitForRequest((r) => r.url().includes(`/places/${PLACE_ID}/menu/`));
    await place.click({ button: 'right' });
    await request;
    await expect(page.getByTestId('target-menu-label')).toContainText('Window table');
    await expect(page.getByRole('menuitem', { name: 'Join' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-place.png', fullPage: false });
    await page.keyboard.press('Escape');
    const join = page.waitForRequest((r) => r.url().includes(`/api/places/${PLACE_ID}/join/`));
    await place.click();
    await join;
  });

  test('inventory card and item title expose their right-click menus without replacing left-click detail', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 1000 });
    await mockRestRoutes(page);
    await page.route('**/api/user/', async (route) => {
      await route.fulfill({
        json: {
          id: 1,
          username: 'test-player',
          display_name: 'Test player',
          email: '',
          email_verified: true,
          last_login: null,
          can_create_characters: false,
          is_staff: false,
          is_gm: false,
          available_characters: [],
          pending_applications: [],
          selected_entry_id: 4,
          selected_entry: { ...CHARACTER, id: 4, character_id: CHARACTER.character_id },
        },
      });
    });
    await page.route('**/api/roster/entries/mine/', async (route) => {
      await route.fulfill({
        json: [{ ...CHARACTER, id: 4, character_id: CHARACTER.character_id }],
      });
    });
    const item = {
      id: ITEM_ID,
      game_object_id: 401,
      template: {
        id: 12,
        name: 'Silver brooch',
        description: 'A small polished brooch.',
        weight: '0.1',
        size: 1,
        value: 0,
        is_container: false,
        is_stackable: false,
        is_consumable: false,
        is_craftable: false,
        image_url: '',
      },
      quality_tier: {
        id: 3,
        name: 'Fine',
        color_hex: '#888888',
        numeric_min: 50,
        numeric_max: 75,
        stat_multiplier: '1.0',
        sort_order: 1,
      },
      suggested_value: 0,
      display_name: 'Silver brooch',
      display_description: 'A small polished brooch.',
      display_image_url: null,
      is_usable: false,
      contained_in: null,
      quantity: 1,
      charges: 0,
      is_open: false,
      access_policy: 'open',
      is_currency_instrument: false,
      can_steal: false,
      crafted_provenance: null,
      accents: [],
      silhouette: null,
    };
    const wornItem = {
      ...item,
      id: WARDROBE_WORN_ITEM_ID,
      game_object_id: 402,
      template: { ...item.template, id: 13, name: 'Plain cloak' },
      display_name: 'Plain cloak',
      display_description: 'A dark wool cloak.',
    };
    const inventoryResponse = { count: 2, next: null, previous: null, results: [item, wornItem] };
    await page.route('**/api/items/inventory/**', async (route) => {
      await route.fulfill({ json: inventoryResponse });
    });
    await page.route('**/api/items/equipped-items/**', async (route) => {
      await route.fulfill({
        json: {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: 91,
              character: CHARACTER.character_id,
              item_instance: WARDROBE_WORN_ITEM_ID,
              body_region: 'torso',
              equipment_layer: 'base',
              body_region_display: 'Torso',
              equipment_layer_display: 'Base',
            },
          ],
        },
      });
    });
    await page.route('**/api/items/outfits/**', async (route) => {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    });
    await page.route('**/api/items/item-facets/**', async (route) => {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    });
    await page.route('**/api/items/facets/**', async (route) => {
      await route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } });
    });
    await page.route('**/api/items/quality-tiers/**', async (route) => {
      await route.fulfill({ json: [] });
    });
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/items/${ITEM_ID}/menu/**`,
      async (route) => {
        await route.fulfill({ json: INVENTORY_ITEM_MENU });
      }
    );
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/items/${WARDROBE_WORN_ITEM_ID}/menu/**`,
      async (route) => {
        await route.fulfill({ json: WARDROBE_WORN_MENU });
      }
    );
    await page.goto('/wardrobe');
    const card = page.getByRole('button', { name: /Silver brooch/ }).first();
    await expect(card).toBeVisible();
    const cardMenuRequest = page.waitForRequest((request) =>
      request
        .url()
        .includes(`/api/actions/characters/${CHARACTER.character_id}/items/${ITEM_ID}/menu/`)
    );
    await card.click({ button: 'right' });
    await cardMenuRequest;
    await expect(page.getByTestId('target-menu-label')).toContainText('Silver brooch');
    for (const action of ['Equip', 'Give…', 'Put in…', 'Drop']) {
      await expect(page.getByRole('menuitem', { name: action, exact: true })).toBeVisible();
    }
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-inventory-card.png', fullPage: false });
    await page.keyboard.press('Escape');
    const wornCard = page.getByRole('button', { name: /Plain cloak/i }).last();
    await expect(wornCard).toBeVisible();
    await wornCard.click({ button: 'right' });
    await expect(page.getByTestId('target-menu-label')).toContainText('Plain cloak');
    for (const action of ['Unequip', 'Give…', 'Put in…', 'Drop']) {
      await expect(page.getByRole('menuitem', { name: action, exact: true })).toBeVisible();
    }
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-wardrobe-worn-item.png',
      fullPage: false,
    });
    await page.keyboard.press('Escape');
    await card.click();
    await expect(page.getByText('A small polished brooch.')).toBeVisible();
    const title = page.getByRole('button', { name: 'Item actions for Silver brooch', exact: true });
    await expect(title).toBeVisible();
    await page.waitForTimeout(600);
    await title.focus();
    await page.keyboard.press('Shift+F10');
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-item-detail.png', fullPage: false });
  });

  test('right-click reads the server-owned target assertion; left-click still drills into the item', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await readyWithVisibleWornItem(page);

    await page.getByRole('button', { name: /Nyx/ }).last().click();
    await expect(page.getByRole('heading', { name: 'Nyx' })).toBeVisible();
    const wornItem = page.getByRole('button', { name: /Silver brooch/i });
    await expect(wornItem).toBeVisible();

    const menuRequest = page.waitForRequest((request) =>
      request
        .url()
        .includes(`/api/actions/characters/${CHARACTER.character_id}/items/${ITEM_ID}/menu/`)
    );
    await wornItem.click({ button: 'right' });
    const request = await menuRequest;
    const requestUrl = new URL(request.url());
    expect(requestUrl.searchParams.get('owner_persona_id')).toBe(String(OWNER_PERSONA_ID));
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-worn-row.png', fullPage: false });

    await page.keyboard.press('Escape');
    await wornItem.click();
    await expect(page.getByRole('heading', { name: 'Silver brooch' })).toBeVisible();
  });
});
