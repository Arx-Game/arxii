import { test, expect, type Page, type WebSocketRoute } from '@playwright/test';

// #3856 PR 1: a look result, a mistyped command, an item line, an arrival, a
// narrative emit and a departure each reach the web client as a typed `text`
// frame and render as a note in the column, in both readers; the Here panel
// lists you first and pressing your row sends `look me`. REST and the socket
// are fixtures (the same shape as `game-entry.spec.ts` and
// `narrative-play-delivery.spec.ts`); the Python tests pin the server's typing.

const CHARACTER = {
  id: 1,
  name: 'Tehom',
  character_id: 18,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

const NYX = { dbref: '#50', name: 'Nyx', thumbnail_url: null, commands: [] as string[] };

const SCENE = {
  id: 1,
  name: 'Evening in the courtyard',
  description: '',
  is_owner: false,
  has_unseen_observer: false,
};

type WireFrame = [string, unknown[], Record<string, unknown>];

async function mockRestRoutes(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/user/') {
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
          selected_entry_id: 1,
          selected_entry: CHARACTER,
        },
      });
    } else if (path === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [CHARACTER] });
    } else if (path === '/api/interactions/') {
      await route.fulfill({ json: { results: [], next: null } });
    } else if (path === '/api/magic/character-resonances/') {
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

interface Connection {
  route: WebSocketRoute;
  sent: string[];
}

/** Reaches "In world" with or without an active scene; returns the socket to push frames on. */
async function reachReadySession(page: Page, withScene: boolean): Promise<Connection> {
  const connection: Connection = { route: undefined as unknown as WebSocketRoute, sent: [] };
  await page.routeWebSocket('**', (route) => {
    connection.route = route;
    route.onMessage((message) => connection.sent.push(String(message)));
  });
  await page.goto('/game');
  await expect(page.getByRole('textbox')).toBeEnabled();
  await expect(page.getByText('Waiting for location', { exact: true })).toBeVisible();
  connection.route.send(
    JSON.stringify([
      'room_state',
      [],
      {
        room: { dbref: '#2', name: 'Quiet courtyard', description: 'Rain rests on the stones.' },
        characters: [NYX],
        objects: [],
        exits: [{ dbref: '#3', name: 'east', thumbnail_url: null, commands: ['east'] }],
        scene: withScene ? SCENE : null,
      },
    ])
  );
  connection.route.send(
    JSON.stringify([
      'puppet_changed',
      [],
      { session_id: 162, character_id: 18, character_name: 'Tehom' },
    ])
  );
  await expect(page.getByText('In world', { exact: true })).toBeVisible();
  return connection;
}

/** A `text` frame the way the server sends it: Evennia's tuple form lands as the frame's kwargs. */
function text(line: string, kwargs: Record<string, unknown> = {}): string {
  return JSON.stringify(['text', [line], kwargs]);
}

function sentCommands(connection: Connection): string[] {
  return connection.sent
    .map((raw) => JSON.parse(raw) as WireFrame)
    .filter(([type]) => type === 'text')
    .map(([, args]) => String(args[0]));
}

/** The kind of every note in the document, in order. */
async function noteKinds(page: Page): Promise<string[]> {
  return page
    .locator('[data-testid="feed-note"]')
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute('data-kind') ?? ''));
}

test.describe('typed text frames become notes in the column (#3856)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockRestRoutes(page);
  });

  test('no scene: look, mistype, item, arrival, ambience and departure each land as a note', async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const connection = await reachReadySession(page, false);
    const editor = page.getByRole('textbox');

    // The player looks at the room; the server answers with the appearance typed look.
    await editor.fill('/look');
    await editor.press('Enter');
    expect(sentCommands(connection)).toContain('look');
    connection.route.send(
      text('Quiet courtyard<br>Rain rests on the stones. Nyx is here.<br>Exits: east', {
        type: 'look',
      })
    );
    const reader = page.getByTestId('exploration-reader');
    await expect(reader.getByText('Rain rests on the stones. Nyx is here.')).toBeVisible();

    // A mistyped command is Evennia's own wording, typed error, never silent.
    await editor.fill('/lok');
    await editor.press('Enter');
    expect(sentCommands(connection)).toContain('lok');
    connection.route.send(
      text('Command \'lok\' is not available. Maybe you meant "look"?', { type: 'error' })
    );
    await expect(page.getByRole('alert')).toContainText("Command 'lok' is not available.");

    // Picking something up, someone arriving, a narrative emit, someone leaving.
    connection.route.send(text('You pick up a lantern.', { type: 'item' }));
    connection.route.send(text('Nyx arrives from the west.', { type: 'arrive' }));
    connection.route.send(
      // The Portal converts Evennia's |G colour code to HTML before the frame
      // leaves; this is the shape the client actually receives.
      text('<span class="color-010">[GEMIT]</span> A cold wind moves through the courtyard.', {
        type: 'narrative',
      })
    );
    connection.route.send(text('Nyx leaves, heading east.', { type: 'move' }));
    await expect(reader.getByText('Nyx leaves, heading east.')).toBeVisible();

    expect(await noteKinds(page)).toEqual(['look', 'error', 'item', 'arrive', 'ambience', 'move']);
    // Nothing untyped, nothing in a strip: there is no System lane any more
    // (the filter strip's System chip is a different thing, #3856 PR 2).
    await expect(page.getByTestId('system-lane-count')).toHaveCount(0);
    await expect(page.getByTestId('system-lane-messages')).toHaveCount(0);

    // The Here panel lists you first, tagged "you"; pressing the row asks the
    // server what others see when they look at you.
    const youRow = page.getByRole('button', { name: /Tehom\s+you/i });
    await expect(youRow).toBeVisible();
    await youRow.click();
    expect(sentCommands(connection)).toContain('look me');
    connection.route.send(text('Tehom<br>A tall figure in a grey coat.', { type: 'look' }));
    await expect(reader.getByText('A tall figure in a grey coat.')).toBeVisible();

    expect(errors).toEqual([]);
    await page.screenshot({
      path: '../docs/reviews/3856/notes-exploration-1280.png',
      fullPage: true,
    });
  });

  test('scene: notes sit among the poses at their time in Threads and Chronological', async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const connection = await reachReadySession(page, true);

    const at = (secondsAgo: number) => new Date(Date.now() - secondsAgo * 1000).toISOString();
    const pose = (id: number, content: string, timestamp: string) =>
      JSON.stringify([
        'interaction',
        [],
        {
          id,
          persona: { id: 99, name: 'Nyx', thumbnail_url: '' },
          content,
          mode: 'pose',
          timestamp,
          scene_id: 1,
          place_id: null,
          place_name: null,
          receiver_persona_ids: [],
          target_persona_ids: [],
        },
      ]);

    connection.route.send(pose(501, 'Nyx sets a lantern on the wall.', at(30)));
    await expect(page.getByText('Nyx sets a lantern on the wall.')).toBeVisible();
    connection.route.send(text('Nyx<br>A woman in a dark cloak, lantern-lit.', { type: 'look' }));
    connection.route.send(
      text('Command \'lok\' is not available. Maybe you meant "look"?', { type: 'error' })
    );
    await expect(page.getByRole('alert')).toContainText("Command 'lok' is not available.");
    connection.route.send(pose(502, 'Nyx glances up at the sound of footsteps.', at(0)));
    await expect(page.getByText('Nyx glances up at the sound of footsteps.')).toBeVisible();
    connection.route.send(text('Corvin arrives from the east.', { type: 'arrive' }));
    await expect(page.getByText('Corvin arrives from the east.')).toBeVisible();

    // Threads view: the notes sit between the two standalone poses, in order.
    const order = () =>
      page
        .locator('[data-thread-id], [data-feed-row]')
        .evaluateAll((nodes) =>
          nodes.map(
            (node) =>
              (
                node.getAttribute('data-thread-id') ??
                node.getAttribute('data-feed-row') ??
                ''
              ).split(':')[0]
          )
        );
    expect(await order()).toEqual(['legacy', 'note', 'note', 'legacy', 'note']);
    expect(await noteKinds(page)).toEqual(['look', 'error', 'arrive']);
    await page.screenshot({
      path: '../docs/reviews/3856/notes-scene-threads-1280.png',
      fullPage: true,
    });

    // Chronological view: the same column, flat.
    await page.getByRole('button', { name: 'Chronological', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Threads', exact: true })).toBeVisible();
    await expect(page.getByText('Corvin arrives from the east.')).toBeVisible();
    expect(await noteKinds(page)).toEqual(['look', 'error', 'arrive']);
    await page.screenshot({
      path: '../docs/reviews/3856/notes-scene-chronological-1280.png',
      fullPage: true,
    });

    // Dark theme: the error note keeps its destructive tokens, the rest stays muted.
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await page.waitForTimeout(300);
    await page.screenshot({
      path: '../docs/reviews/3856/notes-scene-dark-1280.png',
      fullPage: true,
    });

    expect(errors).toEqual([]);
  });

  test('tagged lifecycle, echo and entry-look text adds no notes (#3933)', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const connection = await reachReadySession(page, false);

    connection.route.send(text('You become Tehom.', { type: 'lifecycle', event: 'become' }));
    connection.route.send(text('Tehom waves.', { type: 'pose', interaction_echo: true }));
    connection.route.send(text('Limbo. This is a room.', { type: 'look', on_entry: true }));
    // An ordinary look, untagged, is the control: it still lands as a note.
    connection.route.send(
      text('Quiet courtyard<br>Moss grows between the flagstones.', { type: 'look' })
    );

    const reader = page.getByTestId('exploration-reader');
    await expect(reader.getByText('Moss grows between the flagstones.')).toBeVisible();
    expect(await noteKinds(page)).toEqual(['look']);
    await expect(page.getByText('You become Tehom.')).toHaveCount(0);
    await expect(page.getByText('Tehom waves.')).toHaveCount(0);
    await expect(page.getByText('Limbo. This is a room.')).toHaveCount(0);

    expect(errors).toEqual([]);
  });
});
