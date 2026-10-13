import { test, expect, type Locator, type Page, type WebSocketRoute } from '@playwright/test';

// #4330: every note in the story column (look, item, system, error, arrive,
// move, ambience) takes the reader's Display settings and fills the column the
// way a pose does. Measured as computed styles in a real browser, in both
// readers, after changing the settings through the sidebar's own controls.
// REST and the socket are fixtures, the same shape as `feed-notes.spec.ts`.

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

// Every kind classifyText (game/feedKinds.ts) can give a text frame; an unknown
// or untyped frame is `system`, so these are all the non-pose lines in the column.
const NOTE_KINDS = [
  'look',
  'item',
  'system',
  'error',
  'page',
  'arrive',
  'move',
  'ambience',
  'vision',
] as const;

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

async function reachReadySession(page: Page, withScene: boolean): Promise<WebSocketRoute> {
  let socket: WebSocketRoute | undefined;
  const sent: string[] = [];
  await page.routeWebSocket('**', (route) => {
    socket = route;
    route.onMessage((message) => sent.push(String(message)));
  });
  await page.goto('/game');
  await expect(page.getByRole('textbox')).toBeEnabled();
  // The client counts itself connected only once the puppet is confirmed and a
  // room has arrived, so wait for its puppet request rather than a status label.
  await expect.poll(() => sent.some((frame) => frame.startsWith('["puppet"'))).toBe(true);
  const route = socket as WebSocketRoute;
  route.send(
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
  route.send(
    JSON.stringify([
      'puppet_changed',
      [],
      { session_id: 162, character_id: 18, character_name: 'Tehom' },
    ])
  );
  await expect(page.getByText('In world', { exact: true })).toBeVisible();
  return route;
}

function text(line: string, kwargs: Record<string, unknown>): string {
  return JSON.stringify(['text', [line], kwargs]);
}

/** One of each note kind, the way the server types them. */
function sendEveryNote(socket: WebSocketRoute): void {
  socket.send(
    text('Quiet courtyard<br>Rain rests on the stones, and the lamps burn low.', { type: 'look' })
  );
  socket.send(text('You pick up a lantern.', { type: 'item' }));
  socket.send(text('Connected to the game.', { type: 'system' }));
  socket.send(text("Command 'lok' is not available.", { type: 'error' }));
  socket.send(text('Nyx arrives from the west.', { type: 'arrive' }));
  socket.send(text('Nyx leaves, heading east.', { type: 'move' }));
  socket.send(text('Nyx pages: Meet me by the east gate.', { type: 'page' }));
  socket.send(
    text('A voice like falling water: the gate will not hold.', {
      type: 'narrative',
      category: 'visions',
    })
  );
  socket.send(text('A cold wind moves through the courtyard.', { type: 'narrative' }));
}

/** The reader's settings, read off the root the way every reader reads them. */
async function readerSettings(page: Page): Promise<{ size: string; family: string }> {
  return page.evaluate(() => {
    const probe = document.createElement('span');
    probe.style.fontSize = 'var(--play-prose-size)';
    probe.style.fontFamily = 'var(--play-prose-family)';
    document.body.appendChild(probe);
    const style = getComputedStyle(probe);
    const result = { size: style.fontSize, family: style.fontFamily };
    probe.remove();
    return result;
  });
}

/** The computed size and face of a note's text, where its words are drawn. */
async function noteText(page: Page, kind: string): Promise<{ size: string; family: string }> {
  return page
    .locator(`[data-testid="feed-note"][data-kind="${kind}"] .whitespace-pre-wrap`)
    .first()
    .evaluate((node) => {
      const style = getComputedStyle(node);
      return { size: style.fontSize, family: style.fontFamily };
    });
}

async function width(locator: Locator): Promise<number> {
  return locator.evaluate((node) => node.getBoundingClientRect().width);
}

/** The column's content width: what a line may fill once the padding is taken off. */
async function columnContentWidth(column: Locator): Promise<number> {
  return column.evaluate((node) => {
    const style = getComputedStyle(node);
    return (
      node.getBoundingClientRect().width -
      parseFloat(style.paddingLeft) -
      parseFloat(style.paddingRight)
    );
  });
}

async function setDisplay(page: Page, size: string, font: 'sans' | 'serif'): Promise<void> {
  const settings = page.locator('details', { hasText: 'Display settings' });
  if (!(await settings.evaluate((node) => (node as HTMLDetailsElement).open))) {
    await settings.locator('summary').click();
  }
  await settings.getByLabel('Prose text size').fill(size);
  await settings.getByLabel('Prose font').selectOption(font);
  await settings.getByLabel('Line length').selectOption('full');
}

async function expectNotesFollow(page: Page): Promise<void> {
  const reader = await readerSettings(page);
  for (const kind of NOTE_KINDS) {
    expect(await noteText(page, kind), `${kind} note text`).toEqual(reader);
  }
}

test.describe('feed notes take the Display settings and fill the column (#4330)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await mockRestRoutes(page);
  });

  test('quiet room: every note follows text size, font and line length', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const socket = await reachReadySession(page, false);
    sendEveryNote(socket);
    const column = page.getByTestId('exploration-reader').locator(':scope > div');
    await expect(column.getByText('A cold wind moves through the courtyard.')).toBeVisible();

    await setDisplay(page, '19', 'serif');
    expect(await readerSettings(page)).toEqual(expect.objectContaining({ size: '19px' }));
    await expectNotesFollow(page);
    const look = page.locator('[data-testid="feed-note"][data-kind="look"]');
    expect(await width(look)).toBeGreaterThanOrEqual((await columnContentWidth(column)) - 1);
    await page.screenshot({
      path: '../docs/reviews/4330/quiet-room-19px-serif-1280.png',
      fullPage: true,
    });

    await setDisplay(page, '13', 'sans');
    expect(await readerSettings(page)).toEqual(expect.objectContaining({ size: '13px' }));
    await expectNotesFollow(page);
    expect(errors).toEqual([]);
  });

  test('scene: every note matches the poses around it, and fills the column', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const socket = await reachReadySession(page, true);
    const at = (secondsAgo: number) => new Date(Date.now() - secondsAgo * 1000).toISOString();
    socket.send(
      JSON.stringify([
        'interaction',
        [],
        {
          id: 501,
          persona: { id: 99, name: 'Nyx', thumbnail_url: '' },
          content: 'Nyx sets a lantern on the wall and looks out at the rain.',
          mode: 'pose',
          timestamp: at(30),
          scene_id: 1,
          place_id: null,
          place_name: null,
          receiver_persona_ids: [],
          target_persona_ids: [],
        },
      ])
    );
    const pose = page.getByText('Nyx sets a lantern on the wall and looks out at the rain.');
    await expect(pose).toBeVisible();
    sendEveryNote(socket);
    const column = page.getByLabel('Story reader').locator(':scope > div');
    await expect(column.getByText('A cold wind moves through the courtyard.')).toBeVisible();

    await setDisplay(page, '19', 'serif');
    await expectNotesFollow(page);
    const poseStyle = await pose.evaluate((node) => {
      const style = getComputedStyle(node);
      return { size: style.fontSize, family: style.fontFamily };
    });
    expect(await noteText(page, 'look')).toEqual(poseStyle);
    expect(await noteText(page, 'system')).toEqual(poseStyle);
    const look = page.locator('[data-testid="feed-note"][data-kind="look"]');
    expect(await width(look)).toBeGreaterThanOrEqual((await columnContentWidth(column)) - 1);
    await page.screenshot({
      path: '../docs/reviews/4330/scene-19px-serif-1280.png',
      fullPage: true,
    });

    await setDisplay(page, '13', 'sans');
    await expectNotesFollow(page);
    expect(errors).toEqual([]);
  });
});
