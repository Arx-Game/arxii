import { test, expect } from '@playwright/test';
import { mockRestRoutes, reachReadySession, type Connection } from './support/gameHarness';

// #3858: a pose or a say reads as a whole sentence with its actor in it. The
// server sends the rendered `line` beside the raw `content`; the reader shows
// the line as the body with the leading name set heavier, and the card above
// it stays metadata. One journey over the demo's feed (issue #3858, demo v1):
// a pose, a say, an emit, a companion pose and a whisper pushed over the
// fixture socket, exactly as `push_interaction` shapes them.

interface Line {
  id: number;
  persona: { id: number; name: string; thumbnail_url: string };
  content: string;
  line: string;
  mode: string;
  target_persona_ids?: number[];
  receiver_persona_ids?: number[];
  attributed_companion_id?: number | null;
  attributed_companion_name?: string | null;
}

function push(connection: Connection, row: Line, minute: number): void {
  connection.route.send(
    JSON.stringify([
      'interaction',
      [],
      {
        timestamp: `2026-09-15T02:${String(minute).padStart(2, '0')}:00Z`,
        scene_id: 1,
        place_id: null,
        place_name: null,
        receiver_persona_ids: [],
        target_persona_ids: [],
        language_id: null,
        language_name: null,
        attributed_companion_id: null,
        attributed_companion_name: null,
        reply_to: null,
        thread_id: null,
        root_thread_id: null,
        ...row,
      },
    ])
  );
}

const TEHOM = { id: 18, name: 'Tehom', thumbnail_url: '' };
const NYX = { id: 99, name: 'Nyx', thumbnail_url: '' };

test.describe('the actor in the line (#3858)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test('a pose, a say, an emit, a companion pose and a whisper read as sentences', async ({
    page,
  }) => {
    await mockRestRoutes(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page);

    // Screens 1 and 2: a pose and a say.
    push(
      connection,
      {
        id: 901,
        persona: TEHOM,
        content: 'stops at the edge of the plaza, hood up.',
        line: 'Tehom stops at the edge of the plaza, hood up.',
        mode: 'pose',
      },
      1
    );
    push(
      connection,
      {
        id: 902,
        persona: TEHOM,
        content: 'Rain again.',
        line: 'Tehom says, "Rain again."',
        mode: 'say',
      },
      2
    );
    const pose = page.locator('[data-testid="pose-unit"]').filter({ hasText: 'hood up' });
    await expect(pose.getByTestId('actor-line')).toHaveText(
      'Tehom stops at the edge of the plaza, hood up.'
    );
    await expect(pose.getByTestId('actor-line')).toHaveAttribute('data-actor', 'Tehom');
    await expect(pose.getByTestId('actor-line').locator('.font-semibold')).toHaveText('Tehom');
    await expect(page.getByTestId('actor-line').nth(1)).toHaveText('Tehom says, "Rain again."');
    await page.waitForTimeout(300);
    await page.screenshot({ path: '../docs/reviews/3858/feed-sentences-1280.png', fullPage: true });

    // Screens 3 and 6: an emit is its own text; a companion pose reads as the companion.
    push(
      connection,
      {
        id: 903,
        persona: NYX,
        content: 'The bells go quiet, one by one.',
        line: 'The bells go quiet, one by one.',
        mode: 'emit',
      },
      3
    );
    push(
      connection,
      {
        id: 904,
        persona: TEHOM,
        content: 'lifts his head, ears back.',
        line: 'Hask lifts his head, ears back.',
        mode: 'pose',
        attributed_companion_id: 7,
        attributed_companion_name: 'Hask',
      },
      4
    );
    const emit = page.locator('[data-testid="pose-unit"]').filter({ hasText: 'bells go quiet' });
    await expect(emit.getByTestId('actor-line')).toHaveText('The bells go quiet, one by one.');
    await expect(emit.getByTestId('actor-line')).not.toHaveAttribute('data-actor', /.+/);
    const companion = page.locator('[data-testid="pose-unit"]').filter({ hasText: 'ears back' });
    await expect(companion.getByTestId('actor-line')).toHaveAttribute('data-actor', 'Hask');
    await expect(companion.getByTestId('companion-owner-tell')).toHaveText('(via Tehom)');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: '../docs/reviews/3858/feed-sentences-emit-companion-1280.png',
      fullPage: true,
    });

    // Screen 4: a whisper in its own thread reads as a sentence too.
    push(
      connection,
      {
        id: 905,
        persona: NYX,
        content: 'Not here.',
        line: 'Nyx whispers, "Not here."',
        mode: 'whisper',
        receiver_persona_ids: [18],
        target_persona_ids: [18],
      },
      5
    );
    await expect(page.getByText('Nyx whispers, "Not here."')).toBeVisible();
    expect(errors).toEqual([]);
  });
});
