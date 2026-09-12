import { expect, type Page, type WebSocketRoute } from '@playwright/test';

/**
 * Shared `/game` Playwright harness (#3761 Task 7).
 *
 * Extracted from `narrative-play-delivery.spec.ts` (#3760 Task 14, kept
 * as-is there — this module mirrors its `mockRestRoutes`/`reachReadySession`
 * fixtures exactly rather than modifying that file) so a second spec file
 * can reach the same "In world" ready state without duplicating the
 * fixture/mock-WS shape or inventing a parallel one. Extended for #3761
 * Task 7 with `mockRestRoutes`'s `activeEncounterId` option and
 * `pushForeignPose` — this codebase has no WS-pushed "encounter start"
 * event; `GamePage`'s `useEncounterForScene` learns of an active encounter
 * purely via polling `GET /api/combat/?scene=<id>` (`src/combat/queries.ts`),
 * so simulating one is a REST-mock concern, not a WS one.
 */

export const CHARACTER = {
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

export const NYX = { dbref: '#50', name: 'Nyx', thumbnail_url: null, commands: [] as string[] };

/** One open game WebSocket connection, as captured by `page.routeWebSocket`. */
export interface Connection {
  route: WebSocketRoute;
  sent: string[];
}

export type WireFrame = [string, unknown[], Record<string, unknown>];

/** Every frame this connection's page has sent so far, parsed as `[type, args, kwargs]`. */
export function frames(connection: Connection): WireFrame[] {
  return connection.sent.map((raw) => JSON.parse(raw) as WireFrame);
}

/** Every `execute_action` frame with the given action name this connection sent, unwrapped to its kwargs. */
export function executeActionFrames(
  connection: Connection,
  action: string
): Record<string, unknown>[] {
  return frames(connection)
    .filter(([type, , kwargs]) => type === 'execute_action' && kwargs.action === action)
    .map(([, , kwargs]) => kwargs.kwargs as Record<string, unknown>);
}

export interface MockRestRoutesOptions {
  /**
   * When set, `GET /api/combat/?scene=<sceneId>` (`useEncounterForScene`)
   * returns one active (non-completed) encounter with this id, instead of
   * the empty-list default — #3761 Task 7's stand-in for "an encounter has
   * started," since nothing pushes that over the WebSocket.
   */
  activeEncounterId?: number;
}

/**
 * Mocks the REST surface `/game` needs to reach a puppeted, in-world
 * session: account + roster (identical shape to `game-entry.spec.ts`'s
 * fixture) plus an empty scene-interactions page so `useSceneInteractions`'s
 * REST leg resolves cleanly — journeys feed the actual interaction/thread
 * data over the mocked WebSocket instead. Anything else 404s, the same
 * fallback `game-entry.spec.ts` uses.
 */
export async function mockRestRoutes(
  page: Page,
  options: MockRestRoutesOptions = {}
): Promise<void> {
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
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
    } else if (path === '/api/combat/' && options.activeEncounterId != null) {
      // useEncounterForScene (#3761) — the ONLY channel by which the client
      // learns of an active encounter; EncounterListItem's other fields are
      // read at most for `.status` here, so a minimal-but-plausible row is
      // enough (CombatRail's own child queries handle a 404 on the encounter
      // DETAIL endpoint below gracefully, rendering "Failed to load
      // encounter." rather than crashing — the tab strip itself doesn't
      // depend on that data).
      // fetchEncountersForScene expects a DRF-paginated envelope
      // (`{ results, count }`), not a bare array — matches the shape
      // `/api/interactions/` returns just above.
      await route.fulfill({
        json: {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: options.activeEncounterId,
              scene: Number(url.searchParams.get('scene') ?? 0),
              encounter_type: 'party_combat',
              status: 'declaring',
              outcome: '',
              completed_at: null,
              round_number: 1,
              pace_mode: 'standard',
              pace_timer_minutes: 0,
              is_paused: false,
              participant_count: 1,
              opponent_count: 1,
            },
          ],
        },
      });
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
 * character (Nyx, with a real dbref) and an active scene so callers can open
 * a conversation tab, or (Task 7) reach an active encounter, without a
 * second room_state round trip.
 */
export async function reachReadySession(page: Page): Promise<Connection[]> {
  const connections: Connection[] = [];
  // #3760 demo-fidelity review Finding 3 — the real backend's
  // `at_post_puppet` (`src/typeclasses/characters.py`) unconditionally calls
  // `send_room_state()` on EVERY puppet, including the reconnect-open
  // handler's `@ic <character>` re-puppet (`useGameSocket.ts`'s `connect()`
  // open listener), not just the very first connect. Without a matching
  // reply here, a reconnect's `lifecycleState` is stuck at `'entering'`
  // forever — `dispatchIncomingMessage` only advances it to
  // `'ready-scene'`/`'ready-no-scene'` on a `room_state` frame — so
  // `GameWindow`'s `playReady` never recovers and the composer stays
  // disabled past what any real backend would produce. Echo the most
  // recently sent `room_state` frame back on every connection AFTER the
  // first one's own `@ic <character>` — the very first connection's initial
  // `room_state` is still driven explicitly below.
  let lastRoomStateFrame: string | null = null;
  await page.routeWebSocket('**', (route) => {
    const connection: Connection = { route, sent: [] };
    const isReconnect = connections.length > 0;
    connections.push(connection);
    route.onMessage((message) => {
      const raw = String(message);
      connection.sent.push(raw);
      if (!isReconnect || !lastRoomStateFrame) return;
      try {
        const [type, args] = JSON.parse(raw) as WireFrame;
        if (type === 'text' && args[0] === `@ic ${CHARACTER.name}`) {
          route.send(lastRoomStateFrame);
        }
      } catch {
        /* Not a frame this echo cares about. */
      }
    });
  });

  await page.goto('/game');
  const editor = page.getByRole('textbox');
  await expect(editor).toBeEnabled();
  await expect(page.getByText('Entering world', { exact: true })).toBeVisible();

  const initialRoomState = JSON.stringify([
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
  ]);
  lastRoomStateFrame = initialRoomState;
  connections[0].route.send(initialRoomState);
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
 * Pushes a fake incoming `interaction` frame from another persona into the
 * room feed — the same wire shape `narrative-play-delivery.spec.ts`'s own
 * fixtures already use for a whisper/pose delivered from Nyx, reused here
 * (#3761 Task 7) rather than inventing a second shape. Defaults to an
 * ordinary room pose from Nyx; pass `overrides` to vary id/content/etc.
 */
export function pushForeignPose(
  connection: Connection,
  overrides: Partial<{
    id: number;
    content: string;
    sceneId: number;
  }> = {}
): void {
  connection.route.send(
    JSON.stringify([
      'interaction',
      [],
      {
        id: overrides.id ?? 902,
        persona: { id: 99, name: NYX.name, thumbnail_url: '' },
        content: overrides.content ?? 'Nyx glances toward the noise, unhurried.',
        mode: 'pose',
        timestamp: new Date().toISOString(),
        scene_id: overrides.sceneId ?? 1,
        place_id: null,
        place_name: null,
        receiver_persona_ids: [],
        target_persona_ids: [],
      },
    ])
  );
}
