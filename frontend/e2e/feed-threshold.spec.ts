import { test, expect, type Page } from '@playwright/test';
import {
  NYX,
  frames,
  mockRestRoutes,
  reachReadySession,
  type Connection,
} from './support/gameHarness';

// #3867: participation begins with the first pose. A present character who
// has not posed is listed in the Here panel with a mark, the composer shows
// the entrance as a state until the viewer's first pose, and that pose goes
// out as the entrance. One journey over the demo's screens (issue #3867, demo
// v1) against the fixture socket; the panel, the composer and the mark are the
// real ones. The threshold refusal (screen 3) has no web affordance to reach
// from here (a target is added from a pose or a thread, which a threshold
// character has none of), so it is pinned by `tagReachability.test.ts` and
// the server's own tests instead.

const SCENE = {
  id: 1,
  name: 'Evening in the courtyard',
  description: '',
  is_owner: false,
  has_unseen_observer: false,
};

function roomState(viewerEntered: boolean, nyxInScene: boolean): string {
  return JSON.stringify([
    'room_state',
    [],
    {
      room: { dbref: '#2', name: 'Quiet courtyard', description: 'Rain rests on the stones.' },
      characters: [{ ...NYX, in_scene: nyxInScene }],
      objects: [],
      exits: [],
      scene: { ...SCENE, viewer_entered: viewerEntered },
    },
  ]);
}

function sentText(connection: Connection): string[] {
  return frames(connection)
    .filter(([type]) => type === 'text')
    .map(([, args]) => String(args[0]));
}

async function typeLine(page: Page, line: string): Promise<void> {
  const editor = page.getByRole('textbox');
  await editor.fill(line);
  await editor.press('Enter');
}

test.describe('at the threshold (#3867)', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
  });

  test('the mark, the entrance state, and the first pose', async ({ page }) => {
    await mockRestRoutes(page);
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    const [connection] = await reachReadySession(page);

    // Screen 1: both newcomers are marked, and the composer shows the entrance.
    connection.route.send(roomState(false, false));
    await expect(page.getByTestId('threshold-mark')).toHaveCount(2);
    await expect(page.getByTestId('threshold-mark').first()).toHaveAttribute(
      'title',
      'Not yet in the scene'
    );
    await expect(page.getByTestId('entrance-state')).toHaveText('✨ Entrance');
    await expect(page.getByTestId('entrance-technique-trigger')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Make an entrance' })).toHaveCount(0);
    await page.waitForTimeout(300);
    await page.screenshot({ path: '../docs/reviews/3867/threshold-1280.png', fullPage: true });

    // Screen 2: the first pose goes out as the entrance; the room says so back,
    // and the mark and the state leave.
    const posed: Array<Record<string, unknown>> = [];
    await page.route('**/api/interactions/submit-pose/', async (route) => {
      posed.push(route.request().postDataJSON());
      await route.fulfill({ status: 201, contentType: 'application/json', body: '{"id": 501}' });
    });
    await typeLine(page, 'stops at the edge of the plaza, hood up.');
    await expect.poll(() => posed.length).toBe(1);
    expect(posed[0]).toMatchObject({ pose_kind: 'entry' });
    connection.route.send(roomState(true, false));
    await expect(page.getByTestId('entrance-state')).toHaveCount(0);
    await expect(page.getByTestId('entrance-technique-trigger')).toHaveCount(0);
    await expect(page.getByTestId('threshold-mark')).toHaveCount(1);

    // Screen 5: Nyx's first pose clears her mark.
    connection.route.send(roomState(true, true));
    await expect(page.getByTestId('threshold-mark')).toHaveCount(0);
    await page.waitForTimeout(300);
    await page.screenshot({
      path: '../docs/reviews/3867/threshold-entered-1280.png',
      fullPage: true,
    });

    // A scene pose takes the REST path, never the socket.
    expect(sentText(connection)).not.toContain('pose stops at the edge of the plaza, hood up.');
    expect(errors).toEqual([]);
  });
});
