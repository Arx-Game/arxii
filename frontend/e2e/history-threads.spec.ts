import { test, expect } from '@playwright/test';
import { mockRestRoutes, reachReadySession } from './support/gameHarness';
import type { Interaction } from '@/scenes/types';

/**
 * #3772 Task 5 - demo fidelity evidence: stages the three History-drill-down
 * screens (collapsed row, expanded thread list, anchored reader) in a real
 * browser and screenshots each for the demo-fidelity-reviewer.
 *
 * FIXTURE-BACKED, not live-backend: the dev database is a dump of production
 * and holds zero interactions, so play rows must not be written into it to
 * stage these screens. `mockRestRoutes`/`reachReadySession` (shared with
 * `narrative-play-encounter-reachability.spec.ts`) reach the same "In world"
 * ready state via mocked REST + a mocked WebSocket; the two play endpoints
 * this journey needs (`/api/play/conversations/`, `/api/play/threads/`) and
 * the reference reader's context endpoint (`/api/play/context/`) are routed
 * here with fixture JSON. What is real: the React components (HistoryNavigator,
 * ConversationThreadList, the reader), their CSS, and their interactions
 * (clicking, expanding, navigating). What is fixture: the session and every
 * JSON payload below.
 */

const CONVERSATIONS = {
  results: [
    {
      ref: { kind: 'room', key: 'scene:412' },
      title: 'Scene 412',
      availability: 'retained',
      canRead: true,
      canSend: false,
      sceneId: '412',
      latestVisiblePose: { id: '18', timestamp: '2026-06-14T10:40:00Z' },
      unread: 3,
      directUnread: 0,
    },
  ],
  before: null,
  after: null,
  snapshot: '2026-06-14T12:00:00Z',
};

const THREADS = {
  results: [
    {
      id: 'a1',
      conversation: { kind: 'room', key: 'scene:412' },
      root: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
      firstVisible: { id: '11', timestamp: '2026-06-14T10:00:00Z' },
      latestVisible: { id: '14', timestamp: '2026-06-14T10:20:00Z' },
      opening: 'You came anyway. I did wonder.',
      visiblePoseCount: 4,
      unread: 2,
      directUnread: 0,
    },
    {
      id: 'a2',
      conversation: { kind: 'room', key: 'scene:412' },
      root: { id: '15', timestamp: '2026-06-14T10:25:00Z' },
      firstVisible: { id: '15', timestamp: '2026-06-14T10:25:00Z' },
      latestVisible: { id: '18', timestamp: '2026-06-14T10:40:00Z' },
      opening: 'Keep your voice down. The steward is still at the door.',
      visiblePoseCount: 6,
      unread: 1,
      directUnread: 0,
    },
  ],
  before: null,
  after: null,
  snapshot: '2026-06-14T12:00:00Z',
};

function pose(overrides: Partial<Interaction> & Pick<Interaction, 'id'>): Interaction {
  return {
    persona: { id: 30, name: 'Nyx' },
    content: '',
    mode: 'pose',
    visibility: 'default',
    timestamp: '2026-06-14T10:00:00Z',
    scene: 412,
    reactions: [],
    is_favorited: false,
    place: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
    action_links: [],
    pose_kind: 'standard',
    endorsee_sheet_id: null,
    endorsable_resonances: [],
    pose_endorsers: [],
    my_pose_endorsement: null,
    entry_endorsers: [],
    entry_endorsed_by_me: false,
    ...overrides,
  };
}

// The anchored reader's context fetch for thread a1 (`firstVisible.id === '11'`),
// keyed to CONVERSATIONS' scene:412 and the two opening poses THREADS declares.
const CONTEXT = {
  results: [
    pose({
      id: 11,
      persona: { id: 30, name: 'Nyx' },
      content: 'You came anyway. I did wonder.',
      timestamp: '2026-06-14T10:00:00Z',
    }),
    pose({
      id: 12,
      persona: { id: 7, name: 'Tehom' },
      content: 'I said I would.',
      timestamp: '2026-06-14T10:05:00Z',
    }),
  ],
  threadId: 'a1',
  before: null,
  after: null,
};

test('history thread drill-down, three screens (#3772)', async ({ page }) => {
  await mockRestRoutes(page);
  // Registered AFTER mockRestRoutes's `**/api/**` catch-all - empirically,
  // Playwright's page.route() tries the most-recently-registered matching
  // handler first, so these two win over the catch-all's 404 fallback
  // without needing `route.fallback()` on either side.
  await page.route('**/api/play/conversations/**', (route) =>
    route.fulfill({ json: CONVERSATIONS })
  );
  await page.route('**/api/play/threads/**', (route) => route.fulfill({ json: THREADS }));
  await page.route('**/api/play/context/**', (route) => route.fulfill({ json: CONTEXT }));

  await reachReadySession(page);

  // Reach History mode the way a player does.
  await page
    .getByRole('navigation', { name: 'Sidebar modes' })
    .getByRole('button', { name: 'History', exact: true })
    .click();

  const historyNav = page.getByTestId('history-navigator');
  await expect(historyNav.getByText('Scene 412')).toBeVisible();
  await expect(historyNav.getByRole('button', { name: /^Threads$/ })).toBeVisible();
  const sidebar = page.getByRole('complementary', { name: 'Play sidebar' });
  await page.screenshot({ path: '../docs/reviews/3772-screen1-collapsed.png', fullPage: false });

  await historyNav.getByRole('button', { name: /^Threads$/ }).click();
  await expect(historyNav.getByText(/You came anyway/)).toBeVisible();
  await expect(historyNav.getByText(/2 threads/)).toBeVisible();
  await expect(historyNav.getByText('2', { exact: true })).toBeVisible();
  await sidebar.screenshot({ path: '../docs/reviews/3772-screen2-expanded.png' });

  await historyNav.getByRole('button', { name: /You came anyway/ }).click();
  await expect(page).toHaveURL(/referencePose=11/);
  await expect(page.getByText(/Reading history/)).toBeVisible();
  await expect(
    page.getByTestId('feed-scroll-container').getByText('You came anyway. I did wonder.')
  ).toBeVisible();
  await page.screenshot({ path: '../docs/reviews/3772-screen3-reader.png', fullPage: false });
});
