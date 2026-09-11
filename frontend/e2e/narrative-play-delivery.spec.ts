import { test, expect, type Page, type WebSocketRoute } from '@playwright/test';

/**
 * #3760 Task 14 — Playwright journeys for the narrative-play-delivery
 * safe-drafts/acknowledgement feature (issue #3760).
 *
 * All three journeys below are FIXTURE-BACKED, not live-backend integration:
 * REST endpoints are mocked via `page.route()` and the game WebSocket via
 * `page.routeWebSocket()`, following `game-entry.spec.ts`'s established
 * pattern exactly (account/roster fixture shape, the `**\/api/**` catch-all
 * with a 404 fallback, capturing the socket via `routeWebSocket('**', ...)`).
 * None of them exercise a real Django/Evennia backend or a real database —
 * per the #3750 evidence-report convention, that distinction is called out
 * here rather than left implicit. Backend wire serialization and the actual
 * idempotency/dedup contract are exercised by the Python integration tests;
 * these three prove the BROWSER-side contract: the composer mints/reuses
 * `client_request_id` correctly, gates sending on a real reconnect
 * handshake, and keeps drafts scoped to the right conversation.
 *
 * A note on how "say"/"whisper" mode is reached: `/game`'s room composer
 * starts with `composerMode` unset, and `ModeSelector`'s mode switch is a
 * no-op while `composerMode` itself is unset (`CommandInput.handleModeChange`
 * guards on `!composerMode`) — so driving the UI through the ModeSelector
 * dropdown from a cold start doesn't work. The real, already-wired way a
 * player reaches a locked `say`/`whisper`/`tt` composer is opening a
 * conversation TAB (`ConversationSidebar` -> `GamePage.handleThreadClick` ->
 * `tabKeyToComposerMode`), so these journeys open a whisper (Journeys 1-2)
 * or place (Journey 3) thread the same way a real player would after
 * receiving one.
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

/** One open game WebSocket connection, as captured by `page.routeWebSocket`. */
interface Connection {
  route: WebSocketRoute;
  sent: string[];
}

type WireFrame = [string, unknown[], Record<string, unknown>];

/** Every frame this connection's page has sent so far, parsed as `[type, args, kwargs]`. */
function frames(connection: Connection): WireFrame[] {
  return connection.sent.map((raw) => JSON.parse(raw) as WireFrame);
}

/** Every `execute_action` frame with the given action name this connection sent, unwrapped to its kwargs. */
function executeActionFrames(connection: Connection, action: string): Record<string, unknown>[] {
  return frames(connection)
    .filter(([type, , kwargs]) => type === 'execute_action' && kwargs.action === action)
    .map(([, , kwargs]) => kwargs.kwargs as Record<string, unknown>);
}

/**
 * Mocks the REST surface `/game` needs to reach a puppeted, in-world
 * session: account + roster (identical shape to `game-entry.spec.ts`'s
 * fixture) plus an empty scene-interactions page so `useSceneInteractions`'s
 * REST leg resolves cleanly — the journeys below feed the actual
 * interaction/thread data over the mocked WebSocket instead. Anything else
 * 404s, the same fallback `game-entry.spec.ts` uses.
 */
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
      // RoomAuraPicker/StatusPanel's useCharacterResonances sets
      // throwOnError:true (it backs an always-present read) - an unmocked
      // 404 here throws into the page's error boundary and takes the whole
      // composer down with it, so this needs a real 200 rather than falling
      // through to the generic 404 fallback below.
      await route.fulfill({ json: [] });
    } else {
      await route.fulfill({ status: 404, json: { detail: 'Not provided by this fixture.' } });
    }
  });
}

/**
 * Navigates to `/game`, wires a WebSocket mock that records EVERY connection
 * the page opens (a reconnect opens a second one), and drives the first
 * connection through `room_state` + `puppet_changed` to reach the same
 * "In world" ready state `game-entry.spec.ts` establishes. Seeds one present
 * character (Nyx, with a real dbref) and an active scene so the journeys
 * below can open a conversation tab without a second room_state round trip.
 */
async function reachReadySession(page: Page): Promise<Connection[]> {
  const connections: Connection[] = [];
  await page.routeWebSocket('**', (route) => {
    const connection: Connection = { route, sent: [] };
    route.onMessage((message) => connection.sent.push(String(message)));
    connections.push(connection);
  });

  await page.goto('/game');
  const editor = page.getByRole('textbox');
  await expect(editor).toBeEnabled();
  await expect(page.getByText('Entering world', { exact: true })).toBeVisible();

  connections[0].route.send(
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
  connections[0].route.send(
    JSON.stringify([
      'puppet_changed',
      [],
      { session_id: 162, character_id: 18, character_name: 'Tehom' },
    ])
  );
  await expect(page.getByText('In world', { exact: true })).toBeVisible();
  return connections;
}

/**
 * Delivers a whisper FROM Nyx addressed to the player's own persona, then
 * opens the resulting conversation tab — locking the composer to
 * `whisper -> Nyx` exactly the way replying to a real received whisper
 * would (`tabKeyToComposerMode`). `whisper` dispatches via `executeAction`
 * (Task 10), which is what Journeys 1-2 need to exercise the
 * `client_request_id` idempotency contract at all.
 */
async function openWhisperTab(page: Page, connection: Connection): Promise<void> {
  connection.route.send(
    JSON.stringify([
      'interaction',
      [],
      {
        id: 501,
        persona: { id: 99, name: 'Nyx', thumbnail_url: '' },
        content: 'Meet me outside.',
        mode: 'whisper',
        timestamp: new Date().toISOString(),
        scene_id: 1,
        place_id: null,
        place_name: null,
        receiver_persona_ids: [7],
        target_persona_ids: [],
      },
    ])
  );
  // The thread list lives behind the play sidebar's "Conversations" mode
  // tab (not shown by default - "Here" is) - a divergence from an earlier
  // reading of GamePage.tsx's source alone; confirmed empirically against
  // the rendered page (#3760 Task 14 report).
  await page
    .getByRole('navigation', { name: 'Sidebar modes' })
    .getByRole('button', { name: 'Conversations', exact: true })
    .click();
  const sidebar = page.getByRole('navigation', { name: 'Thread sidebar' });
  await sidebar.getByRole('button', { name: 'Whisper: Nyx', exact: false }).click();
}

test.describe('narrative play delivery (#3760) — fixture-backed journeys', () => {
  test('a dropped send retried with the same id lands exactly once', async ({ page }) => {
    await mockRestRoutes(page);
    // The lookup endpoint never finds a record: the send genuinely never
    // reached (or was never acked by) the backend, so the draft goes
    // unknown -> stranded on reconnect rather than self-healing.
    await page.route('**/api/play/submissions/**', async (route) => {
      await route.fulfill({ status: 404, json: { detail: 'Not found.' } });
    });

    const connections = await reachReadySession(page);
    await openWhisperTab(page, connections[0]);

    const editor = page.getByRole('textbox');
    await editor.fill('Meet me by the fountain.');
    await editor.press('Control+Enter');

    await expect(page.getByTestId('send-pending-banner')).toBeVisible();
    await expect.poll(() => executeActionFrames(connections[0], 'whisper').length).toBe(1);
    const firstAttempt = executeActionFrames(connections[0], 'whisper')[0];
    const firstAttemptId = firstAttempt.client_request_id as string;
    expect(firstAttemptId).toBeTruthy();

    // The ack never arrives on this connection — simulate the connection
    // dropping before it does (an abnormal, non-1000 close code).
    await connections[0].route.close({ code: 1011, reason: 'dropped mid-send' });
    await expect.poll(() => connections.length, { timeout: 10_000 }).toBe(2);

    // Reauthorize + reconcile land on the new connection; the lookup finds
    // nothing, so the draft surfaces as stranded with the same visible text.
    await expect(page.getByTestId('stranded-draft-banner')).toBeVisible();
    await expect(editor).toHaveValue('Meet me by the fountain.');

    await page
      .getByTestId('stranded-draft-banner')
      .getByRole('button', { name: 'Resume & retry', exact: true })
      .click();

    await expect.poll(() => executeActionFrames(connections[1], 'whisper').length).toBe(1);
    const retryAttempt = executeActionFrames(connections[1], 'whisper')[0];

    // The idempotency assertion: the retry reused the ORIGINAL
    // client_request_id (not a fresh one), and across the dropped attempt +
    // the retry only ONE distinct id was ever used — a real backend keyed
    // on this id dedupes the two wire attempts down to a single accepted
    // row, which is what "lands exactly once" means here.
    expect(retryAttempt.client_request_id).toBe(firstAttemptId);
    const allWhisperAttempts = [
      ...executeActionFrames(connections[0], 'whisper'),
      ...executeActionFrames(connections[1], 'whisper'),
    ];
    expect(allWhisperAttempts).toHaveLength(2);
    expect(new Set(allWhisperAttempts.map((a) => a.client_request_id)).size).toBe(1);
    expect(retryAttempt.text).toBe(firstAttempt.text);

    // The retry lands: ack it on the NEW connection and confirm the draft
    // clears exactly once (no leftover banner, no leftover text).
    connections[1].route.send(
      JSON.stringify(['action_result', [], { success: true, message: null, data: null }])
    );
    await expect(page.getByTestId('send-pending-banner')).toHaveCount(0);
    await expect(page.getByTestId('stranded-draft-banner')).toHaveCount(0);
    await expect(editor).toHaveValue('');
  });

  test('a reconnect reauthorizes before flipping to ready', async ({ page }) => {
    await mockRestRoutes(page);

    // Hold the lookup endpoint open on its first call so the test can
    // observe the composer staying disabled WHILE reconciliation is
    // genuinely in flight, then release it under the test's own control.
    let releaseLookup: () => void = () => {};
    const firstLookupGate = new Promise<void>((resolve) => {
      releaseLookup = resolve;
    });
    let lookupCallCount = 0;
    await page.route('**/api/play/submissions/**', async (route) => {
      lookupCallCount += 1;
      if (lookupCallCount === 1) await firstLookupGate;
      await route.fulfill({ status: 404, json: { detail: 'Not found.' } });
    });

    const connections = await reachReadySession(page);
    await openWhisperTab(page, connections[0]);

    const editor = page.getByRole('textbox');
    const sendButton = page.getByRole('button', { name: 'Send', exact: true });
    await editor.fill('Still there?');
    await editor.press('Control+Enter');
    await expect(page.getByTestId('send-pending-banner')).toBeVisible();

    await connections[0].route.close({ code: 1011, reason: 'dropped' });
    await expect(sendButton).toBeDisabled();

    await expect.poll(() => connections.length, { timeout: 10_000 }).toBe(2);
    // Step 1 of useGameSocket's reconnect-open handler — reauthorize (the
    // `@ic` re-puppet) — is sent synchronously, before reconciliation (step
    // 2) even starts.
    await expect
      .poll(() =>
        frames(connections[1]).some(([type, args]) => type === 'text' && args[0] === '@ic Tehom')
      )
      .toBe(true);
    // Reconciliation's lookup call has landed and is being held open — the
    // composer must stay disabled for the whole time it's outstanding, not
    // just at the instant of the close.
    await expect.poll(() => lookupCallCount).toBeGreaterThanOrEqual(1);
    await expect(sendButton).toBeDisabled();

    // Release the held lookup response — only NOW does reconciliation
    // finish and `ready` flip true.
    releaseLookup();
    await expect(sendButton).toBeEnabled();
  });

  test('travel preserves separate drafts per room', async ({ page }) => {
    await mockRestRoutes(page);
    const connections = await reachReadySession(page);

    const editor = page.getByRole('textbox');
    // The thread list lives behind the play sidebar's "Conversations" mode
    // tab (see openWhisperTab's comment on this same divergence).
    await page
      .getByRole('navigation', { name: 'Sidebar modes' })
      .getByRole('button', { name: 'Conversations', exact: true })
      .click();
    const sidebar = page.getByRole('navigation', { name: 'Thread sidebar' });

    // "Room A" — the room's own anchor conversation (no tab open yet).
    await editor.fill('Room A draft: the courtyard is quiet tonight.');

    // "Travel" to a different physical context. A Place thread within the
    // same scene is this codebase's real, currently-wired per-conversation
    // draft boundary (`GameWindow`'s `draftScope` includes the open
    // conversation tab's key, and a Place IS a travel destination within a
    // room — see `PlaceBar`/`travel_to`) — the room composer's OWN
    // draftScope is not keyed by which physical room a character is
    // standing in when no tab is open, only by the open tab, so a Place tab
    // is the real "somewhere else" this UI isolates a draft into.
    connections[0].route.send(
      JSON.stringify([
        'interaction',
        [],
        {
          id: 601,
          persona: { id: 99, name: 'Nyx', thumbnail_url: '' },
          content: 'Something stirs at the Hart.',
          mode: 'pose',
          timestamp: new Date().toISOString(),
          scene_id: 1,
          place_id: 5,
          place_name: 'The Gilded Hart',
          receiver_persona_ids: [],
          target_persona_ids: [],
        },
      ])
    );
    await sidebar.getByRole('button', { name: 'The Gilded Hart', exact: false }).click();

    // "Room B"'s composer starts empty — nothing typed in room A leaked in.
    await expect(editor).toHaveValue('');
    await editor.fill('Room B draft: something else entirely.');

    // Back to room A ("All" re-anchors the composer to the room, mirroring
    // GamePage.handleShowAll) — the original draft is restored verbatim.
    await sidebar.getByRole('button', { name: 'All', exact: true }).click();
    await expect(editor).toHaveValue('Room A draft: the courtyard is quiet tonight.');

    // And room B's own draft survived the round trip too.
    await sidebar.getByRole('button', { name: 'The Gilded Hart', exact: false }).click();
    await expect(editor).toHaveValue('Room B draft: something else entirely.');
  });
});
