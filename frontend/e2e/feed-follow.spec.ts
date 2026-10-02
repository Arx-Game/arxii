import { test, expect, type Locator, type Page } from '@playwright/test';
import {
  mockRestRoutes,
  pushForeignPose,
  reachReadySession,
  type Connection,
  type WireFrame,
} from './support/gameHarness';

// Three things a player met on first logging in from the web page: the feed
// did not follow new lines, the text sat in a narrow strip with empty space
// on both sides, and `/quit` printed its farewell and changed nothing. Each
// depends on something jsdom does not have (a layout engine, a real close
// frame), so the unit tests beside the code cannot see them fail; this runs
// the built page in a browser. REST and the socket are fixtures, the same
// shape as `feed-notes.spec.ts`.

/** A `text` frame the way the server sends it. */
function text(line: string, kwargs: Record<string, unknown> = {}): string {
  return JSON.stringify(['text', [line], kwargs]);
}

/** How many pixels of content sit below the visible part of a scroll container. */
function belowTheFold(container: Locator): Promise<number> {
  return container.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight);
}

/** Whether the container has more content than fits, so "at the bottom" means something. */
function overflows(container: Locator): Promise<boolean> {
  return container.evaluate((el) => el.scrollHeight > el.clientHeight + 200);
}

/** The reader turns the wheel over the feed, the way a player scrolls up to read. */
async function wheel(page: Page, container: Locator, deltaY: number): Promise<void> {
  await container.hover();
  await page.mouse.wheel(0, deltaY);
}

function sentCommands(connection: Connection): string[] {
  return connection.sent
    .map((raw) => JSON.parse(raw) as WireFrame)
    .filter(([type]) => type === 'text')
    .map(([, args]) => String(args[0]));
}

test.describe('the feed follows its newest line', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 800 });
    await mockRestRoutes(page);
  });

  test('quiet room: new lines stay in view until the reader scrolls up', async ({ page }) => {
    const [connection] = await reachReadySession(page, { scene: false });
    const reader = page.getByTestId('exploration-reader');

    for (let line = 1; line <= 60; line += 1) {
      connection.route.send(text(`Rain line ${line}.`, { type: 'narrative' }));
    }
    await expect(reader.getByText('Rain line 60.')).toBeInViewport();
    expect(await overflows(reader)).toBe(true);
    expect(await belowTheFold(reader)).toBeLessThan(2);

    // Scrolled up to read: the next lines must not pull the reader down.
    await wheel(page, reader, -3000);
    await expect.poll(() => belowTheFold(reader)).toBeGreaterThan(200);
    const readingAt = await reader.evaluate((el) => el.scrollTop);
    connection.route.send(text('Rain line 61.', { type: 'narrative' }));
    await expect(reader.getByText('Rain line 61.')).toBeAttached();
    expect(await reader.evaluate((el) => el.scrollTop)).toBe(readingAt);

    // Back at the bottom, the feed follows again.
    await wheel(page, reader, 100_000);
    await expect.poll(() => belowTheFold(reader)).toBeLessThan(2);
    connection.route.send(text('Rain line 62.', { type: 'narrative' }));
    await expect(reader.getByText('Rain line 62.')).toBeInViewport();
    expect(await belowTheFold(reader)).toBeLessThan(2);
  });

  test('scene: poses and notes both stay in view until the reader scrolls up', async ({ page }) => {
    const [connection] = await reachReadySession(page);
    const feed = page.getByTestId('feed-scroll-container');

    for (let pose = 1; pose <= 40; pose += 1) {
      pushForeignPose(connection, { id: 900 + pose, content: `Nyx counts ${pose}.` });
    }
    await expect(feed.getByText('Nyx counts 40.')).toBeInViewport();
    expect(await overflows(feed)).toBe(true);
    await expect.poll(() => belowTheFold(feed)).toBeLessThan(2);

    // A note is not a pose: the count the old effect watched does not change.
    connection.route.send(text('A cold wind moves through the courtyard.', { type: 'narrative' }));
    await expect(feed.getByText('A cold wind moves through the courtyard.')).toBeInViewport();
    await expect.poll(() => belowTheFold(feed)).toBeLessThan(2);

    await wheel(page, feed, -3000);
    await expect.poll(() => belowTheFold(feed)).toBeGreaterThan(200);
    const readingAt = await feed.evaluate((el) => el.scrollTop);
    pushForeignPose(connection, { id: 990, content: 'Nyx counts on, unheard.' });
    // Give the row time to mount and be measured; a follow would land in it.
    await page.waitForTimeout(500);
    expect(await feed.evaluate((el) => el.scrollTop)).toBe(readingAt);
  });
});

test.describe('the text fills the story pane', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 800 });
    await mockRestRoutes(page);
  });

  /** The width of the readers' column against the pane it sits in. */
  async function columnAndPane(page: Page): Promise<{ column: number; pane: number }> {
    return page.evaluate(() => {
      const pane = document.querySelector<HTMLElement>('.play-story-pane');
      const column = document.querySelector<HTMLElement>(
        '[data-testid="exploration-reader"] > div, [aria-label="Story reader"] > div'
      );
      return {
        column: column?.getBoundingClientRect().width ?? 0,
        pane: pane?.getBoundingClientRect().width ?? 0,
      };
    });
  }

  for (const scene of [false, true]) {
    test(`${scene ? 'scene' : 'quiet room'}: the column is as wide as the pane`, async ({
      page,
    }) => {
      await reachReadySession(page, { scene });

      const { column, pane } = await columnAndPane(page);
      expect(pane).toBeGreaterThan(1200);
      // Only the scrollbar's gutter separates the two.
      expect(pane - column).toBeLessThan(32);
    });
  }

  test('Line length: Limited brings the centred measure back', async ({ page }) => {
    await reachReadySession(page, { scene: false });

    await page.getByText('Display settings').click();
    await page.getByLabel('Line length').selectOption('limited');

    const { column, pane } = await columnAndPane(page);
    expect(column).toBeLessThan(pane - 300);
  });
});

test.describe('a typed quit leaves the world', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await mockRestRoutes(page);
  });

  test('the server closes the socket for quit and the client does not come back', async ({
    page,
  }) => {
    const connections = await reachReadySession(page, { scene: false });
    const editor = page.getByRole('textbox');

    await editor.fill('/quit');
    await editor.press('Enter');
    expect(sentCommands(connections[0])).toContain('quit');
    // What the server does with it: the farewell, then a normal close carrying
    // the command's reason.
    connections[0].route.send(text('Quitting. Hope to see you again, soon.'));
    await connections[0].route.close({ code: 1000, reason: 'quit' });

    await expect(page).toHaveURL(/\/hall$/);
    // The first reconnect used to fire a second later and re-puppet.
    await page.waitForTimeout(2500);
    expect(connections).toHaveLength(1);
  });

  test('a normal close with no such reason still reconnects', async ({ page }) => {
    const connections = await reachReadySession(page, { scene: false });

    await connections[0].route.close({ code: 1000 });

    await expect.poll(() => connections.length, { timeout: 5000 }).toBe(2);
    await expect(page).toHaveURL(/\/game$/);
  });
});
