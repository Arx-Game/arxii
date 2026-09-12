import { test, expect } from '@playwright/test';
import { mockRestRoutes, reachReadySession } from './support/gameHarness';
import type { Interaction } from '@/scenes/types';

/**
 * #3772 Task 5 - demo fidelity evidence: stages the History-drill-down
 * screens (collapsed row, expanded thread list, anchored reader, and the
 * empty/temporary conversation states) in a real browser and screenshots
 * each for the demo-fidelity-reviewer.
 *
 * FIXTURE-BACKED, not live-backend: the dev database is a dump of production
 * and holds zero interactions, so play rows must not be written into it to
 * stage these screens. `mockRestRoutes`/`reachReadySession` (shared with
 * `narrative-play-encounter-reachability.spec.ts`) reach the same "In world"
 * ready state via mocked REST + a mocked WebSocket; the three play endpoints
 * this journey needs (`/api/play/conversations/`, `/api/play/threads/`, and
 * the reference reader's `/api/play/context/`) are routed here with fixture
 * JSON. What is real: the React components (HistoryNavigator,
 * ConversationThreadList, the reader), their CSS, and their interactions
 * (clicking, expanding, navigating). What is fixture: the session and every
 * JSON payload below.
 */

// Three conversation rows, matching the approved demo's own examples
// verbatim: a retained scene with reply threads, a retained whisper with
// none, and a temporary scene. Order matters -- it is the on-screen order.
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
    {
      ref: { kind: 'whisper', key: 'whisper:3,9' },
      title: 'Whisper with two others',
      availability: 'retained',
      canRead: true,
      canSend: true,
      sceneId: null,
      latestVisiblePose: { id: '50', timestamp: '2026-06-14T09:00:00Z' },
      unread: 0,
      directUnread: 0,
    },
    {
      ref: { kind: 'room', key: 'scene:398' },
      title: 'Scene 398',
      availability: 'temporary',
      canRead: true,
      canSend: false,
      sceneId: '398',
      latestVisiblePose: { id: '80', timestamp: '2026-06-14T08:00:00Z' },
      unread: 0,
      directUnread: 0,
    },
  ],
  before: null,
  after: null,
  snapshot: '2026-06-14T12:00:00Z',
};

// scene:412's three reply threads, plus a cursor so the per-conversation
// pager renders too (#3772 demo-fidelity review Fix 3: the demo's Screen 2
// shows all three thread rows AND the "Next page" pager in the same
// expanded block).
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
    {
      id: 'a3',
      conversation: { kind: 'room', key: 'scene:412' },
      root: { id: '19', timestamp: '2026-06-14T10:45:00Z' },
      firstVisible: { id: '19', timestamp: '2026-06-14T10:45:00Z' },
      latestVisible: { id: '20', timestamp: '2026-06-14T10:50:00Z' },
      opening: 'Then we are agreed, and neither of us will say so twice.',
      visiblePoseCount: 2,
      unread: 0,
      directUnread: 0,
    },
  ],
  before: null,
  after: 'cursor-threads-2',
  snapshot: '2026-06-14T12:00:00Z',
};

// The whisper conversation has no reply threads at all -- the demo's own
// "No reply threads" / empty-line state (Fix 3).
const EMPTY_THREADS = {
  results: [],
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

// The anchored reader's context fetch for thread a1 (`firstVisible.id ===
// '11'`). #3772 demo-fidelity review Fix 2: the two thread-a1 poses now
// carry `thread_id: 'a1'` -- without it, `ThreadedNarrativeReader`'s
// `poseRoleLabel` (gated on exactly that field) falls back to "Standalone"
// for both, which is what the first evidence round shipped and the review
// caught. Two standalone narration poses precede the thread, and a second,
// EARLIER real thread ('a9', both poses timestamped before a1's) follows a
// realistic window shape (`PlayContextView` really does return a window of
// neighboring poses, not just the two the thread itself owns) -- a9's last
// pose is deliberately earlier than a1's last pose so `mostRecentGroupKey`
// picks 'a1' for the default auto-expand, agreeing with the explicit
// target-thread expand the anchor-seek effect performs; a9 therefore stays
// collapsed by construction, rendering as its own collapsed thread card
// exactly the way a genuine "other thread, collapsed" would.
const CONTEXT = {
  results: [
    pose({
      id: 8,
      persona: { id: 30, name: 'Nyx' },
      content: 'The hall smells of wet stone.',
      timestamp: '2026-06-14T09:45:00Z',
    }),
    pose({
      id: 9,
      persona: { id: 7, name: 'Tehom' },
      content: 'She crosses to the window.',
      timestamp: '2026-06-14T09:50:00Z',
    }),
    pose({
      id: 16,
      thread_id: 'a9',
      persona: { id: 30, name: 'Nyx' },
      content: 'Someone has moved the chairs again.',
      timestamp: '2026-06-14T09:55:00Z',
    }),
    pose({
      id: 17,
      thread_id: 'a9',
      persona: { id: 7, name: 'Tehom' },
      content: 'They always are, near the solstice.',
      timestamp: '2026-06-14T09:58:00Z',
    }),
    pose({
      id: 11,
      thread_id: 'a1',
      persona: { id: 30, name: 'Nyx' },
      content: 'You came anyway. I did wonder.',
      timestamp: '2026-06-14T10:00:00Z',
    }),
    pose({
      id: 12,
      thread_id: 'a1',
      persona: { id: 7, name: 'Tehom' },
      content: 'I said I would.',
      timestamp: '2026-06-14T10:05:00Z',
    }),
  ],
  threadId: 'a1',
  before: null,
  after: null,
};

test('history thread drill-down, four screens (#3772)', async ({ page }) => {
  // Taller than the 1280x720 default: three conversation rows, one expanded
  // to three thread rows plus a pager, do not all fit in 720px of the
  // sidebar's own internal scroll container - a default-height screenshot
  // would silently crop the very rows/pager this evidence exists to show.
  await page.setViewportSize({ width: 1280, height: 1600 });
  await mockRestRoutes(page);
  // Registered AFTER mockRestRoutes's `**/api/**` catch-all - empirically,
  // Playwright's page.route() tries the most-recently-registered matching
  // handler first, so these win over the catch-all's 404 fallback without
  // needing `route.fallback()` on either side.
  await page.route('**/api/play/conversations/**', (route) =>
    route.fulfill({ json: CONVERSATIONS })
  );
  // Threads is conversation-scoped: scene:412 has real reply threads, every
  // other conversation (the whisper, in this journey) has none.
  await page.route('**/api/play/threads/**', (route) => {
    const url = new URL(route.request().url());
    const payload = url.searchParams.get('conversation') === 'scene:412' ? THREADS : EMPTY_THREADS;
    return route.fulfill({ json: payload });
  });
  await page.route('**/api/play/context/**', (route) => route.fulfill({ json: CONTEXT }));

  await reachReadySession(page);

  // Reach History mode the way a player does.
  await page
    .getByRole('navigation', { name: 'Sidebar modes' })
    .getByRole('button', { name: 'History', exact: true })
    .click();

  const historyNav = page.getByTestId('history-navigator');
  const rowLocator = (title: string) =>
    historyNav.locator('.mt-2.rounded.border.p-2').filter({ hasText: title });
  const scene412Row = rowLocator('Scene 412');
  const whisperRow = rowLocator('Whisper with two others');
  const scene398Row = rowLocator('Scene 398');

  // Screen 1: all three conversation rows collapsed, matching the demo's own
  // browse example set (Fix 3).
  await expect(scene412Row.getByText('3 new · Retained')).toBeVisible();
  await expect(whisperRow.getByText('Retained', { exact: true })).toBeVisible();
  await expect(scene398Row.getByText('Temporary · not saved')).toBeVisible();
  await page.screenshot({ path: '../docs/reviews/3772-screen1-collapsed.png', fullPage: false });

  // Screen 2: scene:412 expanded - all three thread rows, their pose counts
  // in the approved day-before-month order, the unread pills, and the
  // per-conversation pager (Fix 1 and Fix 3).
  await scene412Row.getByRole('button', { name: /^Threads$/ }).click();
  await expect(scene412Row.getByRole('button', { name: /^3 threads$/ })).toBeVisible();
  await expect(scene412Row.getByText('You came anyway. I did wonder.')).toBeVisible();
  await expect(scene412Row.getByText('4 poses · 14 Jun')).toBeVisible();
  await expect(scene412Row.getByText('2', { exact: true })).toBeVisible();
  await expect(
    scene412Row.getByText('Keep your voice down. The steward is still at the door.')
  ).toBeVisible();
  await expect(scene412Row.getByText('6 poses · 14 Jun')).toBeVisible();
  await expect(scene412Row.getByText('1', { exact: true })).toBeVisible();
  await expect(
    scene412Row.getByText('Then we are agreed, and neither of us will say so twice.')
  ).toBeVisible();
  await expect(scene412Row.getByText('2 poses · 14 Jun')).toBeVisible();
  await expect(scene412Row.getByRole('button', { name: /next page/i })).toBeVisible();
  const sidebar = page.getByRole('complementary', { name: 'Play sidebar' });
  await sidebar.screenshot({ path: '../docs/reviews/3772-screen2-expanded.png' });

  // Screen 3: press the first thread row - reference mode anchored at its
  // first visible pose, with the demo's central affordance now confirmable:
  // "Opening pose"/"Reply in ..." role labels (Fix 2), a real applied
  // highlight on the anchored pose (not just a screenshot's say-so), and a
  // genuinely collapsed neighboring thread (its later pose stays hidden).
  await scene412Row.getByRole('button', { name: /You came anyway/ }).click();
  await expect(page).toHaveURL(/referencePose=11/);
  await expect(page.getByText(/Reading history/)).toBeVisible();
  const feed = page.getByTestId('feed-scroll-container');
  await expect(feed.getByText('You came anyway. I did wonder.', { exact: true })).toBeVisible();
  await expect(feed.getByText('Opening pose')).toBeVisible();
  await expect(feed.getByText(/Reply in You came anyway/)).toBeVisible();
  // The anchored pose actually carries the highlight the reader applies to
  // a deep-link target - a mechanical check, not a screenshot's say-so.
  await expect(page.locator('[data-pose-id="11"][data-highlighted="true"]')).toBeVisible();
  // The neighboring thread ('a9') is a real second thread, collapsed by
  // default: its root excerpt shows in the collapsed header, but its
  // second pose stays hidden until pressed.
  await expect(feed.getByText(/Someone has moved the chairs again/)).toBeVisible();
  await expect(feed.getByText(/They always are, near the solstice/)).toHaveCount(0);
  await page.screenshot({ path: '../docs/reviews/3772-screen3-reader.png', fullPage: false });

  // Screen 4: the whisper's empty-thread-list state, and the temporary
  // conversation row, side by side (Fix 3). Expanding the whisper's Threads
  // control collapses scene:412's (at most one conversation's threads are
  // open at a time), which is fine - Screen 4 needs neither.
  await whisperRow.getByRole('button', { name: /^Threads$/ }).click();
  await expect(whisperRow.getByRole('button', { name: /No reply threads/i })).toBeVisible();
  await expect(
    whisperRow.getByText('Every pose here stands on its own. Open the conversation to read it.')
  ).toBeVisible();
  await expect(scene398Row.getByText('Temporary · not saved')).toBeVisible();
  await sidebar.screenshot({ path: '../docs/reviews/3772-screen4-states.png' });
});
