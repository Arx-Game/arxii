import { test, expect, type Page, type WebSocketRoute } from '@playwright/test';
import path from 'node:path';

/**
 * #3862 — a pose made of one unbroken run of characters must break at the
 * feed column's edge instead of widening the feed sideways.
 *
 * FIXTURE-BACKED, not live: REST is mocked via `page.route()` and the game
 * WebSocket via `page.routeWebSocket()`, following `game-entry.spec.ts` and
 * `narrative-play-delivery.spec.ts`. The pose arrives over the mocked socket
 * exactly as `push_interaction` would send it, so the reader path under test
 * (`ThreadedNarrativeReader` -> `SceneMessages` -> `PoseUnit` ->
 * `FormattedContent`) is the real one; only the backend is absent.
 *
 * This is the layout assertion the unit tests cannot make: jsdom performs no
 * layout, so `FormattedContent.test.tsx` only pins the utility class. Here a
 * real browser lays the page out, and the test proves both directions — the
 * rule holds with the shipped CSS, and removing that one rule reproduces the
 * sideways overflow — so a green run is evidence of the mechanism, not of
 * the class name.
 */

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

/** A body with no break opportunity anywhere: the shape that overflowed on production. */
const UNBROKEN = 'x'.repeat(500);

/**
 * Where the review-evidence screenshots for #3862 are written: repo-relative
 * `docs/reviews/3862/`, expressed from `frontend/` since Playwright runs there
 * (the other specs write `test-results/...` the same cwd-relative way).
 */
const SHOTS = path.join('..', 'docs', 'reviews', '3862');

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
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

/** Reaches the "In world" state inside an active scene and returns the first socket. */
async function reachReadySession(page: Page): Promise<WebSocketRoute> {
  const routes: WebSocketRoute[] = [];
  await page.routeWebSocket('**', (route) => {
    routes.push(route);
    route.onMessage(() => {
      /* Nothing the page sends matters to this journey. */
    });
  });

  await page.goto('/game');
  await expect(page.getByRole('textbox')).toBeEnabled();
  await expect(page.getByText('Entering world', { exact: true })).toBeVisible();

  routes[0].send(
    JSON.stringify([
      'room_state',
      [],
      {
        room: { dbref: '#2', name: 'Quiet courtyard', description: 'Rain rests on the stones.' },
        characters: [NYX],
        objects: [],
        exits: [],
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
  routes[0].send(
    JSON.stringify([
      'puppet_changed',
      [],
      { session_id: 162, character_id: 18, character_name: 'Tehom' },
    ])
  );
  await expect(page.getByText('In world', { exact: true })).toBeVisible();
  return routes[0];
}

function deliverPose(socket: WebSocketRoute, content: string): void {
  socket.send(
    JSON.stringify([
      'interaction',
      [],
      {
        id: 601,
        persona: { id: 99, name: 'Nyx', thumbnail_url: '' },
        content,
        mode: 'pose',
        timestamp: new Date().toISOString(),
        scene_id: 1,
        place_id: null,
        place_name: null,
        receiver_persona_ids: [],
        target_persona_ids: [],
      },
    ])
  );
}

/**
 * The widest point any text of the pose reaches, against the right edge of the
 * story pane it lives in. Measured on the text's own client rects rather than
 * on an element box, since an overflowing inline run paints past its block's
 * box without changing the box's width.
 */
async function poseOverflowPx(page: Page): Promise<number> {
  return page.evaluate(() => {
    const pose = document.querySelector('[data-testid="pose-unit"]');
    const pane = document.querySelector('.play-story-pane');
    if (!pose || !pane) throw new Error('pose-unit or story pane not rendered');
    const range = document.createRange();
    range.selectNodeContents(pose);
    const rightmost = Math.max(...Array.from(range.getClientRects()).map((r) => r.right));
    return rightmost - pane.getBoundingClientRect().right;
  });
}

test.describe('feed word-wrap (#3862) — fixture-backed layout proof', () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test('an unbroken 500-character pose wraps inside the story pane', async ({ page }) => {
    await mockRestRoutes(page);
    const socket = await reachReadySession(page);
    deliverPose(socket, UNBROKEN);

    const pose = page.getByTestId('pose-unit');
    await expect(pose).toBeVisible();
    await expect(pose).toContainText(UNBROKEN.slice(0, 40));

    // With the shipped CSS: the text stays inside the pane, and neither the
    // document nor the pane has grown a horizontal scroll range.
    expect(await poseOverflowPx(page)).toBeLessThanOrEqual(0);
    const scrolls = await page.evaluate(() => {
      const pane = document.querySelector('.play-story-pane') as HTMLElement;
      return {
        document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        pane: pane.scrollWidth - pane.clientWidth,
      };
    });
    expect(scrolls.document).toBeLessThanOrEqual(0);
    expect(scrolls.pane).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, 'after-1280.png'), fullPage: false });

    // The composer is the same failure one step earlier: a player typing the
    // run must see it wrap in the textarea, not run off the right edge.
    const editor = page.getByRole('textbox');
    await editor.fill(UNBROKEN);
    const editorScroll = await editor.evaluate(
      (el) => (el as HTMLTextAreaElement).scrollWidth - (el as HTMLTextAreaElement).clientWidth
    );
    expect(editorScroll).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, 'after-1280-composer.png'), fullPage: false });
    await editor.fill('');

    // Sensitivity check: remove exactly the rule this change adds, and the
    // same pose overflows the pane again. This is the production failure
    // shape; it is also proof that the assertions above measure the rule and
    // not some other layout accident.
    await page.addStyleTag({
      content: '.\\[overflow-wrap\\:anywhere\\] { overflow-wrap: normal !important; }',
    });
    expect(await poseOverflowPx(page)).toBeGreaterThan(50);
    await page.screenshot({ path: path.join(SHOTS, 'before-1280.png'), fullPage: false });
  });

  test('the same pose wraps at a narrow desktop width', async ({ page }) => {
    await page.setViewportSize({ width: 1040, height: 720 });
    await mockRestRoutes(page);
    const socket = await reachReadySession(page);
    deliverPose(socket, `${UNBROKEN.slice(0, 120)} then ordinary words ${UNBROKEN.slice(0, 200)}`);

    const pose = page.getByTestId('pose-unit');
    await expect(pose).toBeVisible();
    expect(await poseOverflowPx(page)).toBeLessThanOrEqual(0);
    await page.screenshot({ path: path.join(SHOTS, 'after-1040.png'), fullPage: false });
  });
});
