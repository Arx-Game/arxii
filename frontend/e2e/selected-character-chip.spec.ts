import { test, expect, type Page, type WebSocketRoute } from '@playwright/test';
import path from 'node:path';

/**
 * #3859 — the header chip and the Hall's character card state presence from
 * the live session, not from the route.
 *
 * FIXTURE-BACKED, not live: REST is mocked via `page.route()` and the game
 * WebSocket via `page.routeWebSocket()`, following `game-entry.spec.ts` and
 * `narrative-play-delivery.spec.ts`. The journey is the one Dan hit on
 * production: enter the world, then open the Hall from the world menu. That
 * navigation is client-side on purpose: sockets live at module scope and
 * `GamePage` has no teardown (ADR-0295), so the character stays in the world
 * and the header, hidden on `/game`, appears on `/hall` over that live
 * session. A `page.goto('/hall')` would reload the bundle and drop the socket,
 * which is not the case under test.
 */

const CHARACTER = {
  id: 1,
  name: 'Tehom',
  character_id: 18,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
  unread_narrative_count: 0,
  unread_direct: 0,
  has_ambient_unread: false,
  attention_as_of_id: 0,
  lifecycle_state: 'ALIVE',
  roster_type: 'Active',
  character_type: 'PC',
};

const NYX = { dbref: '#50', name: 'Nyx', thumbnail_url: null, commands: [] as string[] };

/** Repo-relative `docs/reviews/3859/`, from `frontend/` where Playwright runs. */
const SHOTS = path.join('..', 'docs', 'reviews', '3859');

async function mockRestRoutes(page: Page): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === '/api/user/') {
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
    } else if (pathname === '/api/roster/entries/mine/') {
      await route.fulfill({ json: [CHARACTER] });
    } else if (pathname === '/api/interactions/') {
      await route.fulfill({ json: { results: [], next: null } });
    } else if (pathname === '/api/magic/character-resonances/') {
      await route.fulfill({ json: [] });
    } else {
      // Same fallback as game-entry.spec.ts: the Hall's plates fall to their
      // own error/empty states on a 404, and the header (this journey's
      // subject) renders regardless.
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

interface Socket {
  route: WebSocketRoute;
  closedByPage: boolean;
}

/** Reaches "In world" on /game and returns the first socket the page opened. */
async function reachReadySession(page: Page): Promise<Socket> {
  const sockets: Socket[] = [];
  await page.routeWebSocket('**', (route) => {
    const socket: Socket = { route, closedByPage: false };
    sockets.push(socket);
    route.onClose(() => {
      socket.closedByPage = true;
    });
    route.onMessage(() => {
      /* Nothing the page sends matters to this journey. */
    });
  });

  await page.goto('/game');
  await expect(page.getByRole('textbox')).toBeEnabled();
  await expect(page.getByText('Waiting for location', { exact: true })).toBeVisible();

  sockets[0].route.send(
    JSON.stringify([
      'room_state',
      [],
      {
        room: { dbref: '#2', name: 'Quiet courtyard', description: 'Rain rests on the stones.' },
        characters: [NYX],
        objects: [],
        exits: [],
        scene: null,
      },
    ])
  );
  sockets[0].route.send(
    JSON.stringify([
      'puppet_changed',
      [],
      { session_id: 162, character_id: 18, character_name: 'Tehom' },
    ])
  );
  await expect(page.getByText('In world', { exact: true })).toBeVisible();
  return sockets[0];
}

/** Opens the Hall the way a player does from inside the world: the world menu's item. */
async function openHallFromWorldMenu(page: Page): Promise<void> {
  await page.getByRole('button', { name: 'Open world menu' }).click();
  await page.getByRole('menuitem', { name: /your characters/i }).click();
  await expect(page).toHaveURL(/\/hall$/);
}

test.describe('selected character chip (#3859) — fixture-backed presence journeys', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('after entering the world, the Hall shows the chip and card as in the world; Leave ends it', async ({
    page,
  }) => {
    await mockRestRoutes(page);
    const socket = await reachReadySession(page);
    await openHallFromWorldMenu(page);

    // The header chip over a live session: the fact the old copy got wrong.
    const header = page.getByRole('banner');
    await expect(header.getByText(/In the world, Quiet courtyard/)).toBeVisible();
    await expect(header.getByRole('link', { name: /return to the world/i })).toHaveAttribute(
      'href',
      '/game'
    );
    await expect(header.getByRole('button', { name: /leave the world/i })).toBeVisible();
    await expect(header.getByRole('link', { name: /enter the world/i })).toHaveCount(0);
    await expect(header.getByText(/Currently Offscreen/)).toHaveCount(0);

    // The Hall's own characters band says the same thing one screen below.
    await expect(page.getByText('In the world', { exact: true })).toBeVisible();
    await page.screenshot({ path: path.join(SHOTS, 'hall-live-1280.png'), fullPage: false });

    // Leave the world from the chip: that character's socket closes (the
    // server unpuppets on the last close), selection stays, the chip and the
    // card flip to the no-session state.
    await header.getByRole('button', { name: /leave the world/i }).click();
    await expect.poll(() => socket.closedByPage).toBe(true);
    await expect(header.getByRole('link', { name: /enter the world/i })).toHaveAttribute(
      'href',
      '/game'
    );
    await expect(header.getByText(/Not in the world/)).toBeVisible();
    await expect(header.getByRole('button', { name: /leave the world/i })).toHaveCount(0);
    await expect(page.getByText('Not in the world', { exact: true })).toBeVisible();
    await expect(header.getByText('Tehom', { exact: true })).toBeVisible();
    await page.screenshot({ path: path.join(SHOTS, 'hall-after-leave-1280.png'), fullPage: false });
  });

  test('a fresh Hall with no session offers Enter the world and says Not in the world', async ({
    page,
  }) => {
    await mockRestRoutes(page);
    await page.routeWebSocket('**', () => {
      /* No socket is expected to open on a cold /hall load. */
    });
    await page.goto('/hall');

    const header = page.getByRole('banner');
    await expect(header.getByRole('link', { name: /enter the world/i })).toHaveAttribute(
      'href',
      '/game'
    );
    await expect(header.getByText(/Not in the world/)).toBeVisible();
    await expect(header.getByRole('button', { name: /leave the world/i })).toHaveCount(0);
    await page.screenshot({ path: path.join(SHOTS, 'hall-no-session-1280.png'), fullPage: false });
  });
});
