import { expect, test, type Page } from '@playwright/test';
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

// Stable evidence captures (written by this spec):
// target-menu-put-in-chooser.png, target-menu-use-target-chooser.png,
// target-menu-join-place.png, target-menu-leave-place.png, target-menu-blocked-go.png,
// target-menu-authored-ignite-menu.png, target-menu-authored-risk.png,
// target-menu-usable-item-menu.png.
const OBJECT_ID = 301;
const USE_TARGET_ITEM_ID = 308;
const COSMETIC_ITEM_ID = 309;
const CARRIED_ITEM_ID = 305;
const LOOSE_ITEM_OBJECT_ID = 307;
const LOOSE_ITEM_INSTANCE_ID = 401;
const EXIT_ID = 302;
const PLACE_JOIN_ID = 303;
const PLACE_LEAVE_ID = 304;
const WORN_ITEM_ID = 306;
const OUTCOME = {
  known: true,
  character_loss_possible: true,
  outcomes: [{ stage: 'Finale', tier: 'CRITICAL_FAILURE', character_loss: true }],
};
const AUTHORED_REF = {
  backend: 'world_interaction',
  challenge_instance_id: null,
  approach_id: null,
  technique_id: null,
  registry_key: null,
  clash_id: null,
  clash_action_slot: null,
  action_slot: null,
  position_id: null,
  blueprint_id: null,
  application_id: 89,
  target_object_id: OBJECT_ID,
};

function authoredEntry() {
  return {
    key: 'authored:0',
    label: 'Ignite',
    group: 'authored',
    // Distinguish the entry ref from PlayerAction.ref to verify authored dispatch authority.
    ref: { ...AUTHORED_REF, application_id: 90 },
    kwargs: {},
    available: true,
    reasons: [],
    inputs: [],
    candidates: [],
    next_candidate_cursor: null,
    action: {
      backend: 'world_interaction',
      display_name: 'Ignite',
      description: 'Light the visible torch with this authored action.',
      difficulty: 'moderate',
      prerequisite_met: true,
      prerequisite_reasons: [],
      check_type: { id: 17, name: 'Mysticism' },
      action_template: null,
      ref: AUTHORED_REF,
      target_spec: null,
      enhancements: [],
      strain: null,
      action_category: null,
      reach: null,
      protective_flavor: null,
      reactive_anima_cost: null,
      position_target_shape: 'none',
      soulfray_warning: null,
      available_fury_tiers: [],
      eligible_fury_anchors: [],
      is_ultimate: false,
    },
    risk: OUTCOME,
  };
}

function entry(key: string, label: string, group: string, options: Record<string, unknown> = {}) {
  return {
    key,
    label,
    group,
    ref: registryRef(key),
    kwargs: { menu_target: { kind: 'objects', target_id: OBJECT_ID } },
    available: true,
    reasons: [],
    inputs: [],
    candidates: [],
    next_candidate_cursor: null,
    action: null,
    risk: null,
    ...options,
  };
}
function menu(
  kind: string,
  id: number,
  label: string,
  entries: object[],
  groups = [{ key: 'items', label: 'Actions' }]
) {
  return {
    actor_id: CHARACTER.character_id,
    target: { kind, target_id: id },
    label,
    groups,
    entries,
  };
}

async function openWardrobeSource(
  page: Page,
  itemId: number,
  label: string,
  entries: Array<Record<string, unknown>>
) {
  await ready(page);
  const item = {
    id: itemId,
    game_object_id: itemId + 100,
    template: {
      id: itemId + 100,
      name: label,
      description: `A ${label.toLowerCase()}.`,
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
    display_name: label,
    display_description: `A ${label.toLowerCase()}.`,
    display_image_url: null,
    is_usable: true,
    contained_in: null,
    quantity: 1,
    charges: 1,
    is_open: false,
    access_policy: 'open',
    is_currency_instrument: false,
    can_steal: false,
    crafted_provenance: null,
    accents: [],
    silhouette: null,
  };
  const containerItems = entries.flatMap((row) => {
    if (!Array.isArray(row.candidates)) return [];
    return row.candidates.flatMap((candidate) => {
      const candidateRow = candidate as Record<string, unknown>;
      const candidateKwargs = candidateRow.kwargs as Record<string, unknown> | undefined;
      const candidateId = candidateKwargs?.container_item_id;
      if (typeof candidateId !== 'number' || typeof candidateRow.label !== 'string') return [];
      const open = candidateRow.available === true;
      return [
        {
          ...item,
          id: candidateId,
          game_object_id: candidateId + 100,
          template: {
            ...item.template,
            id: candidateId + 100,
            name: candidateRow.label,
            is_container: true,
          },
          display_name: candidateRow.label,
          display_description: `A ${candidateRow.label.toLowerCase()}.`,
          is_open: open,
          access_policy: open ? 'open' : 'locked',
        },
      ];
    });
  });
  await page.route('**/api/items/inventory/**', async (route) =>
    route.fulfill({
      json: {
        count: 1 + containerItems.length,
        next: null,
        previous: null,
        results: [item, ...containerItems],
      },
    })
  );
  await page.route('**/api/items/equipped-items/**', async (route) =>
    route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } })
  );
  for (const path of ['outfits', 'item-facets', 'facets']) {
    await page.route(`**/api/items/${path}/**`, async (route) =>
      route.fulfill({ json: { count: 0, next: null, previous: null, results: [] } })
    );
  }
  await page.route('**/api/items/quality-tiers/**', async (route) => route.fulfill({ json: [] }));
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/items/${itemId}/menu/**`,
    async (route) => {
      const inputsFor = new URL(route.request().url()).searchParams.get('inputs_for');
      const visibleEntries = inputsFor ? entries.filter((row) => row.key === inputsFor) : entries;
      await route.fulfill({ json: menu('items', itemId, label, visibleEntries) });
    }
  );
  await page.getByRole('button', { name: 'Items', exact: true }).click();
  await page.getByRole('link', { name: /wardrobe/i }).click();
  await expect(page).toHaveURL(/\/wardrobe$/);
  const card = page.getByRole('button', { name: new RegExp(label) }).first();
  await expect(card).toBeVisible();
  return card;
}

async function ready(page: Page) {
  await page.setViewportSize({ width: 1280, height: 1000 });
  await mockRestRoutes(page);
  await page.route('**/api/user/', async (route) =>
    route.fulfill({
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
    })
  );
  const connectionPromise = reachReadySession(page);
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/objects/${OBJECT_ID}/menu/**`,
    async (route) =>
      route.fulfill({
        json: menu(
          'objects',
          OBJECT_ID,
          'Torch',
          [entry('look_at_object', 'Look', 'perception'), authoredEntry()],
          [
            { key: 'perception', label: 'Perception' },
            { key: 'authored', label: 'Authored actions' },
          ]
        ),
      })
  );
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/personas/99/menu/**`,
    async (route) =>
      route.fulfill({
        json: {
          persona_id: 99,
          is_self: false,
          scene_id: null,
          viewer_persona_id: 7,
          notice: '',
          items: [{ key: 'look', label: 'Look', group: 'perception', available: true, reason: '' }],
          groups: [
            { key: 'perception', empty_state: '' },
            { key: 'conflict', empty_state: '' },
            { key: 'scene', empty_state: '' },
            { key: 'social', empty_state: '' },
          ],
          scene_actions: [],
        },
      })
  );
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/items/${WORN_ITEM_ID}/menu/**`,
    async (route) => {
      const response = menu(
        'items',
        WORN_ITEM_ID,
        'Plain cloak',
        [
          entry('look_at_item', 'Look', 'perception', {
            kwargs: {
              menu_target: {
                kind: 'items',
                target_id: WORN_ITEM_ID,
                owner_persona_id: 99,
              },
            },
          }),
        ],
        [{ key: 'perception', label: 'Perception' }]
      );
      response.target.owner_persona_id = 99;
      await route.fulfill({ json: response });
    }
  );
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/objects/${LOOSE_ITEM_OBJECT_ID}/menu/**`,
    async (route) =>
      route.fulfill({
        json: menu(
          'objects',
          LOOSE_ITEM_OBJECT_ID,
          'Plain cloak',
          [
            entry('look_at_item', 'Look', 'perception', {
              kwargs: { menu_target: { kind: 'items', target_id: LOOSE_ITEM_INSTANCE_ID } },
            }),
            entry('get', 'Get', 'items', {
              kwargs: { menu_target: { kind: 'items', target_id: LOOSE_ITEM_INSTANCE_ID } },
            }),
          ],
          [
            { key: 'perception', label: 'Perception' },
            { key: 'items', label: 'Item handling' },
          ]
        ),
      })
  );
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/exits/${EXIT_ID}/menu/**`,
    async (route) => {
      await route.fulfill({
        json: menu(
          'exits',
          EXIT_ID,
          'North gate',
          [
            entry('traverse_exit', 'Go', 'movement', {
              kwargs: { menu_target: { kind: 'exits', target_id: EXIT_ID } },
              available: false,
              reasons: ['The gate is sealed.'],
            }),
          ],
          [{ key: 'movement', label: 'Movement' }]
        ),
      });
    }
  );
  await page.route('**/api/places/?room=*', async (route) =>
    route.fulfill({
      json: {
        results: [
          {
            id: PLACE_JOIN_ID,
            name: 'Window table',
            description: 'A quiet table.',
            viewer_is_present: false,
          },
          {
            id: PLACE_LEAVE_ID,
            name: 'Stone bench',
            description: 'A low bench.',
            viewer_is_present: true,
          },
        ],
      },
    })
  );
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/places/${PLACE_JOIN_ID}/menu/**`,
    async (route) => {
      await route.fulfill({
        json: menu(
          'places',
          PLACE_JOIN_ID,
          'Window table',
          [
            entry('join_place', 'Join', 'movement', {
              kwargs: { menu_target: { kind: 'places', target_id: PLACE_JOIN_ID } },
            }),
          ],
          [{ key: 'movement', label: 'Movement' }]
        ),
      });
    }
  );
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/places/${PLACE_LEAVE_ID}/menu/**`,
    async (route) => {
      await route.fulfill({
        json: menu(
          'places',
          PLACE_LEAVE_ID,
          'Stone bench',
          [
            entry('leave_place', 'Leave', 'movement', {
              kwargs: { menu_target: { kind: 'places', target_id: PLACE_LEAVE_ID } },
            }),
          ],
          [{ key: 'movement', label: 'Movement' }]
        ),
      });
    }
  );
  let dispatched: unknown = null;
  await page.route(
    `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
    async (route) => {
      dispatched = route.request().postDataJSON();
      await route.fulfill({
        json: {
          backend: 'registry',
          deferred: false,
          success: true,
          message: 'Nyx wears a plain cloak.',
          data: {
            visible_worn_items: [
              {
                id: WORN_ITEM_ID,
                display_name: 'Plain cloak',
                body_region: 'neck',
                equipment_layer: 'accessory',
                owner_persona_id: 99,
              },
            ],
          },
        },
      });
    }
  );
  const [connection] = await connectionPromise;
  connection.route.send(
    JSON.stringify([
      'room_state',
      [],
      {
        room: { dbref: '#2', name: 'Quiet courtyard', description: 'Rain rests on the stones.' },
        characters: [{ ...NYX, persona_id: 99 }],
        objects: [
          { dbref: `#${OBJECT_ID}`, name: 'Torch', thumbnail_url: null },
          { dbref: `#${LOOSE_ITEM_OBJECT_ID}`, name: 'Plain cloak', thumbnail_url: null },
          { dbref: '#88', name: 'Stone statue', thumbnail_url: null },
        ],
        exits: [{ dbref: `#${EXIT_ID}`, name: 'North gate', thumbnail_url: null }],
        scene: {
          id: 1,
          name: 'Evening',
          description: '',
          is_owner: false,
          has_unseen_observer: false,
        },
      },
    ])
  );
  await expect(page.getByRole('button', { name: /Torch/i })).toBeVisible();
  return { dispatched: () => dispatched };
}

test.describe('approved target-menu states (#4032)', () => {
  test('a loose room item offers Look and Get without action on open', async ({ page }) => {
    await ready(page);
    const itemRow = page.getByRole('button', { name: /Plain cloak/i });
    await itemRow.click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Get' })).toBeVisible();
    await page.getByRole('menu').screenshot({ path: 'test-results/fidelity/loose-item-menu.png' });
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-loose-item-get.png', fullPage: false });
  });

  test('Give chooser selects a visible recipient for a carried item', async ({ page }) => {
    const give = entry('give', 'Give', 'items', {
      kwargs: { menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID } },
      inputs: [
        {
          name: 'recipient_persona_id',
          kind: 'recipient',
          required: true,
          target_kind: null,
          default: null,
        },
      ],
      candidates: [
        {
          key: '99',
          label: 'Nyx',
          kwargs: { recipient_persona_id: 99 },
          available: true,
          reasons: [],
        },
      ],
    });
    const source = await openWardrobeSource(page, CARRIED_ITEM_ID, 'Silver brooch', [give]);
    let dispatched: unknown = null;
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
      async (route) => {
        dispatched = route.request().postDataJSON();
        await route.fulfill({ json: { backend: 'registry', deferred: false, success: true } });
      }
    );
    await source.click({ button: 'right' });
    await page.getByRole('menuitem', { name: 'Give…' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('radio', { name: 'Nyx' })).toBeEnabled();
    await page.getByRole('dialog').screenshot({ path: 'test-results/fidelity/give-chooser.png' });
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-give-chooser.png', fullPage: false });
    const request = page.waitForRequest(
      (r) => r.url().includes('/dispatch/') && r.method() === 'POST'
    );
    await page.getByRole('button', { name: 'Give' }).click();
    await request;
    await expect
      .poll(() => dispatched)
      .toMatchObject({
        ref: { registry_key: 'give' },
        kwargs: {
          menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID },
          recipient_persona_id: 99,
        },
      });
  });

  test('no-candidate actions stay disabled with their current safe reasons', async ({ page }) => {
    const source = await openWardrobeSource(page, CARRIED_ITEM_ID, 'Silver brooch', [
      entry('give', 'Give', 'items', {
        kwargs: { menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID } },
        available: false,
        reasons: ['No recipient is currently available.'],
        inputs: [
          {
            name: 'recipient_persona_id',
            kind: 'recipient',
            required: true,
            target_kind: null,
            default: null,
          },
        ],
      }),
      entry('put_in', 'Put in', 'items', {
        kwargs: { menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID } },
        available: false,
        reasons: ['No container is currently available.'],
        inputs: [
          {
            name: 'container_item_id',
            kind: 'container',
            required: true,
            target_kind: null,
            default: null,
          },
        ],
      }),
      entry('use_item', 'Use', 'items', {
        kwargs: { menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID } },
        available: false,
        reasons: ['No valid target or option is currently available.'],
        inputs: [
          {
            name: 'use_target',
            kind: 'target',
            required: true,
            target_kind: 'character',
            default: null,
          },
        ],
      }),
    ]);
    await source.click({ button: 'right' });
    for (const reason of [
      'No recipient is currently available.',
      'No container is currently available.',
      'No valid target or option is currently available.',
    ]) {
      const blocked = page.getByRole('menuitem', { name: new RegExp(reason) });
      await expect(blocked).toBeVisible();
      await expect(blocked).toBeDisabled();
    }
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-no-candidates.png', fullPage: false });
  });

  test('Put-in chooser shows available and blocked containers and dispatches selected container', async ({
    page,
  }) => {
    const putIn = entry('put_in', 'Put in', 'items', {
      kwargs: { menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID } },
      inputs: [
        {
          name: 'container_item_id',
          kind: 'container',
          required: true,
          target_kind: null,
          default: null,
        },
      ],
      candidates: [
        {
          key: '501',
          label: 'Open wicker basket',
          kwargs: { container_item_id: 501 },
          available: true,
          reasons: [],
        },
        {
          key: '502',
          label: 'Locked iron coffer',
          kwargs: { container_item_id: 502 },
          available: false,
          reasons: ['The coffer is locked.'],
        },
      ],
    });
    const source = await openWardrobeSource(page, CARRIED_ITEM_ID, 'Plain cloak', [putIn]);
    let dispatched: unknown = null;
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
      async (route) => {
        dispatched = route.request().postDataJSON();
        await route.fulfill({
          json: {
            backend: 'registry',
            deferred: false,
            success: true,
            message: 'You put the cloak away.',
          },
        });
      }
    );
    await source.click({ button: 'right' });
    await page.getByRole('menuitem', { name: 'Put in…' }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByText('Plain cloak is already selected.')).toBeVisible();
    await expect(page.getByRole('radio', { name: 'Open wicker basket' })).toBeEnabled();
    await expect(page.getByRole('radio', { name: /Locked iron coffer.*locked/i })).toHaveAttribute(
      'disabled',
      ''
    );
    await page.getByRole('dialog').screenshot({ path: 'test-results/fidelity/put-in-chooser.png' });
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-put-in-chooser.png', fullPage: false });
    const request = page.waitForRequest(
      (r) => r.url().includes('/dispatch/') && r.method() === 'POST'
    );
    await page.getByRole('button', { name: 'Put In' }).click();
    await request;
    await expect
      .poll(() => dispatched)
      .toMatchObject({
        ref: { registry_key: 'put_in' },
        kwargs: {
          menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID },
          container_item_id: 501,
        },
      });
  });

  test('chooser loads the next candidate page and dispatches its selected row', async ({
    page,
  }) => {
    const putIn = entry('put_in', 'Put in', 'items', {
      kwargs: { menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID } },
      inputs: [
        {
          name: 'container_item_id',
          kind: 'container',
          required: true,
          target_kind: null,
          default: null,
        },
      ],
      candidates: [
        {
          key: '501',
          label: 'First page basket',
          kwargs: { container_item_id: 501 },
          available: true,
          reasons: [],
        },
      ],
      next_candidate_cursor: 'opaque-next-page',
    });
    const source = await openWardrobeSource(page, CARRIED_ITEM_ID, 'Plain cloak', [putIn]);
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/items/${CARRIED_ITEM_ID}/menu/**`,
      async (route) => {
        const requestUrl = new URL(route.request().url());
        const cursorPage = requestUrl.searchParams.get('candidate_cursor') === 'opaque-next-page';
        const candidate = cursorPage
          ? {
              key: '503',
              label: 'Second page trunk',
              kwargs: { container_item_id: 503 },
              available: true,
              reasons: [],
            }
          : {
              key: '501',
              label: 'First page basket',
              kwargs: { container_item_id: 501 },
              available: true,
              reasons: [],
            };
        await route.fulfill({
          json: menu('items', CARRIED_ITEM_ID, 'Plain cloak', [
            entry('put_in', 'Put in', 'items', {
              kwargs: { menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID } },
              inputs: [
                {
                  name: 'container_item_id',
                  kind: 'container',
                  required: true,
                  target_kind: null,
                  default: null,
                },
              ],
              candidates: [candidate],
              next_candidate_cursor: cursorPage ? null : 'opaque-next-page',
            }),
          ]),
        });
      }
    );
    let dispatched: unknown = null;
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
      async (route) => {
        dispatched = route.request().postDataJSON();
        await route.fulfill({ json: { backend: 'registry', deferred: false, success: true } });
      }
    );
    await source.click({ button: 'right' });
    await page.getByRole('menuitem', { name: 'Put in…' }).click();
    await expect(page.getByRole('radio', { name: 'First page basket' })).toHaveCount(1);
    await page.getByRole('button', { name: 'Load more choices' }).click();
    await expect(page.getByRole('radio', { name: 'Second page trunk' })).toHaveCount(1);
    await page.getByRole('radio', { name: 'Second page trunk' }).check();
    const request = page.waitForRequest(
      (r) => r.url().includes('/dispatch/') && r.method() === 'POST'
    );
    await page.getByRole('button', { name: 'Put In' }).click();
    await request;
    await expect
      .poll(() => dispatched)
      .toMatchObject({
        ref: { registry_key: 'put_in' },
        kwargs: {
          menu_target: { kind: 'items', target_id: CARRIED_ITEM_ID },
          container_item_id: 503,
        },
      });
  });

  test('Use target chooser shows blocked target and dispatches chosen target', async ({ page }) => {
    const use = entry('use_item', 'Use', 'items', {
      kwargs: { menu_target: { kind: 'items', target_id: USE_TARGET_ITEM_ID } },
      inputs: [
        {
          name: 'use_target',
          kind: 'target',
          required: true,
          target_kind: 'character',
          default: null,
        },
      ],
      candidates: [
        {
          key: '77',
          label: 'Nyx',
          kwargs: { use_target: { kind: 'objects', target_id: 50 } },
          available: true,
          reasons: [],
        },
        {
          key: '88',
          label: 'Stone statue',
          kwargs: { use_target: { kind: 'objects', target_id: 88 } },
          available: false,
          reasons: ['Out of reach.'],
        },
      ],
    });
    const menuTarget = { menu_target: { kind: 'items', target_id: USE_TARGET_ITEM_ID } };
    const source = await openWardrobeSource(page, USE_TARGET_ITEM_ID, 'Healing draught', [
      entry('look_at_item', 'Look', 'items', { kwargs: menuTarget }),
      use,
      entry('give', 'Give…', 'items', {
        kwargs: menuTarget,
        inputs: [
          {
            name: 'recipient_persona_id',
            kind: 'recipient',
            required: true,
            target_kind: null,
            default: null,
          },
        ],
        candidates: [
          {
            key: '77',
            label: 'Nyx',
            kwargs: { recipient_persona_id: 77 },
            available: true,
            reasons: [],
          },
        ],
      }),
      entry('drop', 'Drop', 'items', { kwargs: menuTarget }),
    ]);
    let dispatched: unknown = null;
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
      async (route) => {
        dispatched = route.request().postDataJSON();
        await route.fulfill({
          json: {
            backend: 'registry',
            deferred: false,
            success: true,
            message: 'You use the draught.',
          },
        });
      }
    );
    await source.click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Use…', exact: true })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Give…' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Drop' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-usable-item-menu.png',
      fullPage: false,
    });
    await page.getByRole('menuitem', { name: 'Use…', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Use Healing draught' })).toBeVisible();
    await expect(page.getByRole('radio', { name: 'Nyx' })).toBeEnabled();
    await expect(page.getByRole('radio', { name: /Stone statue.*Out of reach/i })).toHaveAttribute(
      'disabled',
      ''
    );
    await page
      .getByRole('dialog')
      .screenshot({ path: 'test-results/fidelity/use-target-chooser.png' });
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-use-target-chooser.png',
      fullPage: false,
    });
    const request = page.waitForRequest(
      (r) => r.url().includes('/dispatch/') && r.method() === 'POST'
    );
    await page.getByRole('button', { name: 'Use' }).click();
    await request;
    await expect
      .poll(() => dispatched)
      .toMatchObject({
        ref: { registry_key: 'use_item' },
        kwargs: {
          menu_target: { kind: 'items', target_id: USE_TARGET_ITEM_ID },
          use_target: { kind: 'objects', target_id: 50 },
        },
      });
  });

  test('cosmetic Use chooser exposes the authored option, optional descriptor, and blend', async ({
    page,
  }) => {
    const use = entry('use_item', 'Use', 'items', {
      kwargs: { menu_target: { kind: 'items', target_id: COSMETIC_ITEM_ID } },
      inputs: [
        { name: 'option_id', kind: 'option', required: true, target_kind: null, default: null },
        { name: 'descriptor', kind: 'text', required: false, target_kind: null, default: null },
        { name: 'blend', kind: 'boolean', required: false, target_kind: null, default: false },
      ],
      candidates: [
        {
          key: '601',
          label: 'Midnight blue',
          kwargs: { option_id: 601 },
          available: true,
          reasons: [],
        },
        {
          key: '602',
          label: 'Unlearned silver',
          kwargs: { option_id: 602 },
          available: false,
          reasons: ['You have not learned this style.'],
        },
      ],
    });
    const source = await openWardrobeSource(page, COSMETIC_ITEM_ID, 'Cosmetic kit', [use]);
    let dispatched: unknown = null;
    await page.route(
      `**/api/actions/characters/${CHARACTER.character_id}/dispatch/`,
      async (route) => {
        dispatched = route.request().postDataJSON();
        await route.fulfill({ json: { backend: 'registry', deferred: false, success: true } });
      }
    );
    await source.click({ button: 'right' });
    await page.getByRole('menuitem', { name: 'Use…', exact: true }).click();
    await expect(page.getByRole('dialog', { name: 'Use Cosmetic kit' })).toBeVisible();
    await expect(page.getByRole('radio', { name: 'Midnight blue' })).toHaveCount(1);
    await expect(
      page.getByRole('radio', { name: /Unlearned silver.*not learned/i })
    ).toHaveAttribute('disabled', '');
    await expect(page.getByRole('radio', { name: 'Midnight blue' })).toBeChecked();
    await expect(page.getByLabel('Appearance description (optional)')).toBeVisible();
    await expect(page.getByLabel('Blend with existing appearance')).toBeVisible();
    await page
      .getByRole('dialog')
      .screenshot({ path: 'test-results/fidelity/cosmetic-use-chooser.png' });
    await page.getByLabel('Appearance description (optional)').fill('A faint silvery sheen');
    await page.getByLabel('Blend with existing appearance').check();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-cosmetic-use.png', fullPage: false });
    const request = page.waitForRequest(
      (r) => r.url().includes('/dispatch/') && r.method() === 'POST'
    );
    await page.getByRole('button', { name: 'Use' }).click();
    await request;
    await expect
      .poll(() => dispatched)
      .toMatchObject({
        ref: { registry_key: 'use_item' },
        kwargs: {
          menu_target: { kind: 'items', target_id: COSMETIC_ITEM_ID },
          option_id: 601,
          descriptor: 'A faint silvery sheen',
          blend: true,
        },
      });
  });

  test('place menus distinguish Leave from Join', async ({ page }) => {
    await ready(page);
    await page.getByRole('button', { name: 'Window table' }).click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Join' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-join-place.png', fullPage: false });
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Stone bench' }).click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Leave' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-leave-place.png', fullPage: false });
  });

  test('blocked Go is visible with its reason and cannot dispatch', async ({ page }) => {
    const { dispatched } = await ready(page);
    await page.getByRole('button', { name: 'North gate' }).last().click({ button: 'right' });
    const go = page.getByRole('menuitem', { name: /Go.*gate is sealed/i });
    await expect(go).toBeVisible();
    await expect(go).toBeDisabled();
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-blocked-go.png', fullPage: false });
    expect(dispatched()).toBeNull();
  });

  test('LookDialog shows only structured viewer-visible worn rows with item menus', async ({
    page,
  }) => {
    await ready(page);
    await page.getByRole('button', { name: /Nyx/i }).last().click({ button: 'right' });
    await page.getByRole('menuitem', { name: 'Look' }).click();
    await expect(page.getByRole('dialog', { name: 'Nyx' })).toBeVisible();
    const wornRow = page.getByRole('button', { name: 'Plain cloak (neck)' });
    await expect(wornRow).toBeVisible();
    await page
      .getByRole('dialog', { name: 'Nyx' })
      .screenshot({ path: 'test-results/fidelity/look-dialog.png' });
    await wornRow.click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await page.getByRole('menu').screenshot({ path: 'test-results/fidelity/worn-item-menu.png' });
    const lookDialogBox = await page.locator('[role="dialog"]').first().boundingBox();
    const itemMenuBox = await page.getByRole('menu').boundingBox();
    if (lookDialogBox === null || itemMenuBox === null) {
      throw new Error('The worn-item menu and LookDialog must both remain visible.');
    }
    const clipX = Math.max(0, Math.floor(Math.min(lookDialogBox.x, itemMenuBox.x) - 12));
    const clipY = Math.max(0, Math.floor(Math.min(lookDialogBox.y, itemMenuBox.y) - 12));
    const clipRight = Math.ceil(
      Math.max(lookDialogBox.x + lookDialogBox.width, itemMenuBox.x + itemMenuBox.width) + 12
    );
    const clipBottom = Math.ceil(
      Math.max(lookDialogBox.y + lookDialogBox.height, itemMenuBox.y + itemMenuBox.height) + 12
    );
    await page.screenshot({
      path: 'test-results/fidelity/look-dialog-with-item-menu.png',
      clip: { x: clipX, y: clipY, width: clipRight - clipX, height: clipBottom - clipY },
    });
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-look-dialog-worn-row.png',
      fullPage: false,
    });
  });

  test('authored action displays risk before confirmed dispatch', async ({ page }) => {
    const { dispatched } = await ready(page);
    await page.getByRole('button', { name: /Torch/i }).click({ button: 'right' });
    await expect(page.getByRole('menuitem', { name: 'Look' })).toBeVisible();
    await expect(page.getByRole('menuitem', { name: 'Ignite' })).toBeVisible();
    await page.waitForTimeout(250);
    await page.screenshot({
      path: 'test-results/target-menu-authored-ignite-menu.png',
      fullPage: false,
    });
    await page.getByRole('menuitem', { name: 'Ignite' }).click();
    await expect(page.getByText('Character loss is possible.')).toBeVisible();
    await expect(page.getByText(/Finale: critical failure \(character loss\)/i)).toBeVisible();
    await page
      .getByRole('dialog')
      .screenshot({ path: 'test-results/fidelity/authored-risk-dialog.png' });
    await page.waitForTimeout(250);
    await page.screenshot({ path: 'test-results/target-menu-authored-risk.png', fullPage: false });
    expect(dispatched()).toBeNull();
    const request = page.waitForRequest(
      (r) => r.url().includes('/dispatch/') && r.method() === 'POST'
    );
    await page.getByRole('button', { name: 'Confirm action' }).click();
    await request;
    await expect.poll(dispatched).toMatchObject({
      ref: {
        backend: 'world_interaction',
        application_id: 89,
        target_object_id: OBJECT_ID,
      },
      kwargs: {},
    });
  });
});
