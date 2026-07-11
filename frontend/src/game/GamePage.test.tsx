import { screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, vi, beforeEach, afterEach, expect } from 'vitest';
import { GamePage } from './GamePage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import {
  startSession,
  setActiveSession,
  setSessionRoom,
  setSessionScene,
  addSceneInteraction,
  clearSceneInteractions,
  resetGame,
} from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';
import type { InteractionWsPayload } from '@/hooks/types';

const ACTIVE_NAME = 'Aria';

// ---------------------------------------------------------------------------
// Mock the roster query — GamePage now derives `personaId` from it directly
// (lifted from GameWindow, #2156 review fold-in) and GameWindow/PoseUnit's
// sub-components (ReactionStrip, PersonaContextMenu, EndorsementControl) all
// call the same hook.
// ---------------------------------------------------------------------------

const rosterEntry: MyRosterEntry = {
  id: 1,
  name: ACTIVE_NAME,
  character_id: 42,
  profile_picture_url: null,
  primary_persona_id: 7,
  active_persona_id: 7,
};

// A second puppet (#2156 review fix — multi-puppet threading/baseline tests
// below need a real second roster entry so `active` can validly switch to it).
const SECOND_NAME = 'Bianca';
const rosterEntry2: MyRosterEntry = {
  id: 2,
  name: SECOND_NAME,
  character_id: 43,
  profile_picture_url: null,
  primary_persona_id: 8,
  active_persona_id: 8,
};

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [rosterEntry, rosterEntry2],
    isLoading: false,
    isError: false,
  })),
  // The character-card drawer (#2156 Task 7) always mounts (persona is null
  // unless an avatar was clicked) and calls these — stub them out since this
  // test suite isn't exercising the drawer's own identity resolution.
  useRosterEntryByNameQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  useRosterEntryQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
}));

// ---------------------------------------------------------------------------
// Mock the REST interaction backfill (useSceneInteractions calls this) so the
// test doesn't hit the network — the WS-seeded interaction below is enough to
// exercise the merged feed.
// ---------------------------------------------------------------------------

vi.mock('@/scenes/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/scenes/queries')>();
  return {
    ...actual,
    fetchInteractions: vi.fn(() => Promise.resolve({ results: [], next: undefined })),
    postInteractionReaction: vi.fn().mockResolvedValue(null),
    fetchReactionEmojiCatalog: vi.fn().mockResolvedValue([]),
    fetchPendingUnlinkedActions: vi.fn(() => Promise.resolve([])),
  };
});

// ---------------------------------------------------------------------------
// Scene toolset (#2156 Task 6): ConsentPrompt/ActionPanel/PendingActionAttachments
// are self-fetching components with heavy internal query machinery unrelated to
// this test's concern (toolset mounting + isAtPlace wiring) — stubbed out as
// lightweight divs, mirroring SceneDetailPage.test.tsx's proven pattern. PlaceBar
// is stubbed too: `isAtPlace` is derived by GamePage's OWN `['scene-places', ...]`
// query (query-reuse, not a callback prop), so exercising it only requires
// controlling `fetchPlaces` — it doesn't require PlaceBar's real render tree.
// ---------------------------------------------------------------------------

vi.mock('@/scenes/components/ConsentPrompt', () => ({
  ConsentPrompt: () => <div data-testid="consent-prompt">ConsentPrompt</div>,
}));

vi.mock('@/scenes/components/PlaceBar', () => ({
  PlaceBar: () => <div data-testid="place-bar">PlaceBar</div>,
}));

vi.mock('@/scenes/components/ActionPanel', () => ({
  ActionPanel: () => <div data-testid="action-panel">ActionPanel</div>,
}));

vi.mock('@/scenes/components/PendingActionAttachments', () => ({
  PendingActionAttachments: () => (
    <div data-testid="pending-action-attachments">PendingActionAttachments</div>
  ),
}));

const mockFetchPlaces = vi.fn((_sceneId: string) =>
  Promise.resolve({
    results: [] as Array<{
      id: number;
      name: string;
      description: string;
      viewer_is_present: boolean;
    }>,
  })
);

vi.mock('@/scenes/actionQueries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/scenes/actionQueries')>();
  return {
    ...actual,
    fetchPlaces: (...args: Parameters<typeof actual.fetchPlaces>) => mockFetchPlaces(...args),
  };
});

// PoseUnit → PersonaContextMenu pulls in combat/queries for the duel-challenge
// affordance; mirrors PoseUnit.test.tsx's mock to keep it from firing real fetches.
vi.mock('@/combat/queries', () => ({
  useOutcomeDetails: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  useDispatchPlayerAction: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false }),
  useEncounterForScene: vi.fn().mockReturnValue({ data: null, isLoading: false, isError: false }),
  combatKeys: { duelChallengesAll: () => ['combat', 'duel-challenges'] },
}));

vi.mock('@/battles/queries', () => ({
  useBattleForSceneQuery: vi.fn().mockReturnValue({ data: null, isLoading: false, isError: false }),
}));

// EndorsementControl mounts its own hook machinery per-pose (#1138); stubbed
// here since this test is about feed/threading composition, not endorsements.
vi.mock('@/scenes/components/EndorsementControl', () => ({
  EndorsementControl: () => null,
}));

function seedActiveSceneWithPose() {
  store.dispatch(startSession(ACTIVE_NAME));
  store.dispatch(
    setSessionScene({
      character: ACTIVE_NAME,
      scene: {
        id: 100,
        name: 'The Grand Ballroom',
        description: '',
        is_owner: false,
        has_unseen_observer: false,
      },
    })
  );
  const interaction: InteractionWsPayload = {
    id: 1,
    persona: { id: 7, name: ACTIVE_NAME, thumbnail_url: '' },
    content: 'stretches languidly.',
    mode: 'pose',
    timestamp: '2026-01-01T00:00:00Z',
    scene_id: 100,
    place_id: null,
    place_name: null,
    receiver_persona_ids: [],
    target_persona_ids: [],
  };
  store.dispatch(addSceneInteraction({ character: ACTIVE_NAME, interaction }));
}

// Seeds a second, distinct thread (a whisper to persona 9) alongside the room
// pose from seedActiveSceneWithPose, so a test can click a thread and assert
// the feed actually narrows to it (#2156 review fix).
function seedWhisperThread() {
  const interaction: InteractionWsPayload = {
    id: 2,
    persona: { id: 7, name: ACTIVE_NAME, thumbnail_url: '' },
    content: 'meet me by the fountain at midnight.',
    mode: 'whisper',
    timestamp: '2026-01-01T00:01:00Z',
    scene_id: 100,
    place_id: null,
    place_name: null,
    receiver_persona_ids: [9],
    target_persona_ids: [],
  };
  store.dispatch(addSceneInteraction({ character: ACTIVE_NAME, interaction }));
}

// Seeds both room AND scene (#2156 Task 6) — real ROOM_STATE broadcasts always
// carry both together (see handleRoomStatePayload.ts), and GamePage derives the
// Place-bar/isAtPlace room id from `session.room.id`, so the toolset needs a
// seeded room to mount PlaceBar and derive `isAtPlace` at all.
function seedActiveSceneWithRoom() {
  store.dispatch(startSession(ACTIVE_NAME));
  store.dispatch(
    setSessionRoom({
      character: ACTIVE_NAME,
      room: {
        id: 55,
        name: 'The Grand Ballroom',
        description: '',
        thumbnail_url: null,
        characters: [],
        objects: [],
        exits: [],
        is_owner: false,
        is_public: true,
        hub: null,
      },
    })
  );
  store.dispatch(
    setSessionScene({
      character: ACTIVE_NAME,
      scene: {
        id: 100,
        name: 'The Grand Ballroom',
        description: '',
        is_owner: false,
        has_unseen_observer: false,
      },
    })
  );
}

describe('GamePage', () => {
  beforeEach(() => {
    store.dispatch(setAccount(null));
  });

  afterEach(() => {
    store.dispatch(resetGame());
  });

  it('prompts to log in when not authenticated', () => {
    renderWithProviders(<GamePage />);
    expect(screen.getByText(/you must be logged in/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /log in/i })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: /register/i })).toHaveAttribute('href', '/register');
  });

  it('shows game interface when authenticated', () => {
    store.dispatch(setAccount(mockAccount));
    renderWithProviders(<GamePage />);
    expect(screen.queryByText(/you must be logged in/i)).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Structured chat-bubble scene feed + threading sidebar (#2156)
  // ---------------------------------------------------------------------------

  describe('structured scene feed + threading sidebar', () => {
    it('renders a pose-unit bubble and the thread sidebar when a scene is active', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();

      renderWithProviders(<GamePage />);

      expect(await screen.findByTestId('pose-unit')).toBeInTheDocument();
      expect(screen.getByLabelText('Thread sidebar')).toBeInTheDocument();
    });

    it('clicking a thread in the sidebar actually filters the center feed (review fix)', async () => {
      // #2165 update: clicking a non-room thread row now OPENS A TAB
      // (GamePage's handleThreadClick dispatches openThreadTab) rather than
      // toggling useThreading's local enabledThreadKeys filter — that old
      // narrowing mechanism is retired for the /game room feed (it still
      // backs /scenes/:id's SceneInteractionPanel, untouched here). The feed
      // narrows because the active TAB drives `tabInteractions` now, and the
      // way back to the full feed is the room row, not "All" (clicking "All"
      // only clears the retired enabledThreadKeys filter, which no longer
      // drives what's on screen once a tab is active — see the "conversation
      // tabs (#2165)" describe block below for that contract's own coverage).
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);

      // Both interactions show before any thread is selected.
      expect(await screen.findByText('stretches languidly.')).toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperButton = within(sidebar)
        .getByText(/whisper/i)
        .closest('button');
      expect(whisperButton).not.toBeNull();
      await user.click(whisperButton as HTMLElement);

      // Clicking the whisper thread opens its tab and narrows the feed to
      // just that thread — the room pose disappears and the whisper stays.
      expect(screen.queryByText('stretches languidly.')).not.toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();

      // The room row restores the full feed (the room anchor).
      const roomButton = within(sidebar).getByText('The Grand Ballroom').closest('button');
      await user.click(roomButton as HTMLElement);
      expect(screen.getByText('stretches languidly.')).toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();
    });

    it('marks the selected thread seen as it grows, while other threads accumulate unread badges (#2156)', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);

      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');

      // Baseline: both threads existed at scene load, so neither shows unread yet.
      const roomButton = () =>
        within(sidebar).getByText('The Grand Ballroom').closest('button') as HTMLElement;
      const whisperButton = () =>
        within(sidebar)
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;

      await waitFor(() => {
        expect(within(roomButton()).queryByText(/^[1-9]/)).not.toBeInTheDocument();
        expect(within(whisperButton()).queryByText(/^[1-9]/)).not.toBeInTheDocument();
      });

      // Select the whisper thread — it's now the actively-viewed thread.
      await user.click(whisperButton());

      // A new pose arrives in the (unselected) room thread from someone else.
      store.dispatch(
        addSceneInteraction({
          character: ACTIVE_NAME,
          interaction: {
            id: 3,
            persona: { id: 99, name: 'Bystander', thumbnail_url: '' },
            content: 'glances over curiously.',
            mode: 'pose',
            timestamp: '2026-01-01T00:02:00Z',
            scene_id: 100,
            place_id: null,
            place_name: null,
            receiver_persona_ids: [],
            target_persona_ids: [],
          },
        })
      );

      // The room thread's badge increments; the selected whisper thread stays at 0.
      await waitFor(() => {
        expect(within(roomButton()).getByText('1')).toBeInTheDocument();
      });
      expect(within(whisperButton()).queryByText(/^[1-9]/)).not.toBeInTheDocument();
    });

    it('badges a brand-new thread that appears mid-session from its very first message (#2156 review fix)', async () => {
      // Regression for a reviewer-caught defect: the old per-thread-KEY
      // baseline zeroed out a brand-new thread's unread count the instant it
      // was first observed (it baselined to the thread's own first message
      // id), so a first-ever whisper never showed a badge. The fix baselines
      // the SCENE once at load instead, so a thread with no prior
      // `threadLastSeen` entry falls back to that scene baseline and counts
      // unread from message one.
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);

      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');
      const roomButton = () =>
        within(sidebar).getByText('The Grand Ballroom').closest('button') as HTMLElement;

      // Pre-existing room thread: no unread at scene load (the baseline was
      // captured, zeroing it out).
      await waitFor(() => {
        expect(within(roomButton()).queryByText(/^[1-9]/)).not.toBeInTheDocument();
      });

      // A brand-new whisper thread arrives mid-session — the very first
      // message anyone has ever sent in it, from someone other than the
      // viewer, while it's unselected.
      store.dispatch(
        addSceneInteraction({
          character: ACTIVE_NAME,
          interaction: {
            id: 5,
            persona: { id: 42, name: 'Mysterious Stranger', thumbnail_url: '' },
            content: 'psst -- a word, in private.',
            mode: 'whisper',
            timestamp: '2026-01-01T00:05:00Z',
            scene_id: 100,
            place_id: null,
            place_name: null,
            receiver_persona_ids: [7],
            target_persona_ids: [],
          },
        })
      );

      const whisperButton = () =>
        within(sidebar)
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;

      // The new thread badges unread from its first message, not 0.
      await waitFor(() => {
        expect(within(whisperButton()).getByText('1')).toBeInTheDocument();
      });

      // Selecting it clears the badge.
      await user.click(whisperButton());
      await waitFor(() => {
        expect(within(whisperButton()).queryByText(/^[1-9]/)).not.toBeInTheDocument();
      });
    });

    it('keeps the scene baseline across ordinary ROOM_STATE churn, so a first-ever whisper still badges (#2156 review fix 2)', async () => {
      // Regression for a reviewer-caught defect: `clearSceneInteractions` used
      // to null `sceneBaselineId` unconditionally, and
      // `handleRoomStatePayload` dispatches it on EVERY ROOM_STATE broadcast —
      // which the backend sends on ordinary room movement (anyone
      // entering/leaving), not just scene changes. GamePage's one-shot
      // baseline ref never re-fires for the same scene id, so the baseline
      // stayed null for the rest of the scene and new-thread badging died.
      // Fix: `clearSceneInteractions` no longer touches `sceneBaselineId` —
      // only an actual scene-id change (via `setSessionScene`) resets it.
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();

      renderWithProviders(<GamePage />);

      await screen.findByText('stretches languidly.');

      // Simulate room churn: someone enters/leaves, the backend broadcasts
      // ROOM_STATE for the SAME scene, and handleRoomStatePayload dispatches
      // clearSceneInteractions.
      store.dispatch(clearSceneInteractions(ACTIVE_NAME));

      const sidebar = screen.getByLabelText('Thread sidebar');

      // A first-ever whisper arrives after the churn, from someone other than
      // the viewer, while it's unselected.
      store.dispatch(
        addSceneInteraction({
          character: ACTIVE_NAME,
          interaction: {
            id: 5,
            persona: { id: 42, name: 'Mysterious Stranger', thumbnail_url: '' },
            content: 'psst -- a word, in private.',
            mode: 'whisper',
            timestamp: '2026-01-01T00:05:00Z',
            scene_id: 100,
            place_id: null,
            place_name: null,
            receiver_persona_ids: [7],
            target_persona_ids: [],
          },
        })
      );

      const whisperButton = () =>
        within(sidebar)
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;

      // The new thread still badges unread from its first message — the
      // scene baseline survived the churn.
      await waitFor(() => {
        expect(within(whisperButton()).getByText('1')).toBeInTheDocument();
      });
    });

    it('resets the thread filter when the active puppet moves into a new scene (#2156 review fix 4)', async () => {
      // Regression: useThreading's selectedThreadKey/enabledThreadKeys are
      // local component state that never reset on their own — GamePage is a
      // single long-lived composition root (unlike SceneDetailPage, which
      // remounts on route change). A thread filter picked in the OLD scene
      // must not silently keep hiding interactions once the puppet moves
      // into a brand-new scene.
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);
      await screen.findByText('stretches languidly.');

      const sidebar = () => screen.getByLabelText('Thread sidebar');
      const whisperButton = () =>
        within(sidebar())
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;

      // Filter down to just the whisper thread — the room pose is hidden.
      await user.click(whisperButton());
      expect(screen.queryByText('stretches languidly.')).not.toBeInTheDocument();

      // The puppet moves into an entirely new scene.
      store.dispatch(
        setSessionScene({
          character: ACTIVE_NAME,
          scene: {
            id: 300,
            name: 'The Garden',
            description: '',
            is_owner: false,
            has_unseen_observer: false,
          },
        })
      );
      store.dispatch(
        addSceneInteraction({
          character: ACTIVE_NAME,
          interaction: {
            id: 10,
            persona: { id: 7, name: ACTIVE_NAME, thumbnail_url: '' },
            content: 'strolls among the roses.',
            mode: 'pose',
            timestamp: '2026-01-01T00:10:00Z',
            scene_id: 300,
            place_id: null,
            place_name: null,
            receiver_persona_ids: [],
            target_persona_ids: [],
          },
        })
      );

      // The stale whisper-only filter from the OLD scene must not hide the
      // new scene's room pose.
      await waitFor(() => {
        expect(screen.getByText('strolls among the roses.')).toBeInTheDocument();
      });
    });

    it("preserves puppet A's accumulated unread badge across a round trip through puppet B's different scene (#2156 review fix 3)", async () => {
      // Regression: the old baseline gate was a single ref keyed only on
      // sceneId. Puppet A (scene 100, badge already accumulated) -> puppet B
      // (scene 200) -> back to puppet A re-triggered the baseline effect
      // (the ref now held "200") and wiped A's badge back to 0. Gating on the
      // per-puppet Redux `sceneBaselineId == null` instead means A's own
      // baseline, once set, survives any number of puppet round trips.
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();
      store.dispatch(startSession(SECOND_NAME));
      store.dispatch(
        setSessionScene({
          character: SECOND_NAME,
          scene: {
            id: 200,
            name: 'The Kitchen',
            description: '',
            is_owner: false,
            has_unseen_observer: false,
          },
        })
      );
      // startSession(SECOND_NAME) above made Bianca active — switch back to
      // Aria before rendering (this test starts with Aria in view).
      store.dispatch(setActiveSession(ACTIVE_NAME));

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);
      await screen.findByText('stretches languidly.');

      const sidebar = () => screen.getByLabelText('Thread sidebar');
      const roomButton = () =>
        within(sidebar()).getByText('The Grand Ballroom').closest('button') as HTMLElement;
      const whisperButton = () =>
        within(sidebar())
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;

      await waitFor(() => {
        expect(within(roomButton()).queryByText(/^[1-9]/)).not.toBeInTheDocument();
      });

      // Select the whisper thread so the (now unselected) room thread
      // accumulates unread from a new arrival.
      await user.click(whisperButton());
      store.dispatch(
        addSceneInteraction({
          character: ACTIVE_NAME,
          interaction: {
            id: 3,
            persona: { id: 99, name: 'Bystander', thumbnail_url: '' },
            content: 'glances over curiously.',
            mode: 'pose',
            timestamp: '2026-01-01T00:02:00Z',
            scene_id: 100,
            place_id: null,
            place_name: null,
            receiver_persona_ids: [],
            target_persona_ids: [],
          },
        })
      );
      await waitFor(() => {
        expect(within(roomButton()).getByText('1')).toBeInTheDocument();
      });

      // Round-trip through puppet B, who is in a completely different scene.
      store.dispatch(setActiveSession(SECOND_NAME));
      store.dispatch(setActiveSession(ACTIVE_NAME));

      // Puppet A's room-thread badge must still read 1 — not wiped by the
      // round trip.
      await waitFor(() => {
        expect(within(roomButton()).getByText('1')).toBeInTheDocument();
      });
    });

    it('badges the first message of a scene that had zero interactions at load (#2156 review fix 2)', async () => {
      // Regression for a reviewer-caught defect: GamePage stored `null` as the
      // baseline for a scene with zero interactions at load — indistinguishable
      // from "the baseline effect hasn't run yet" — so `countUnread` fell
      // through to its no-baseline branch (0 unread) and the scene's first
      // message never badged. Fix: store `0` as the "baselined empty" sentinel
      // (interaction ids are DB pks and never 0), and `countUnread` treats any
      // number, including 0, as a live threshold.
      store.dispatch(setAccount(mockAccount));
      store.dispatch(startSession(ACTIVE_NAME));
      store.dispatch(
        setSessionScene({
          character: ACTIVE_NAME,
          scene: {
            id: 200,
            name: 'An Empty Hall',
            description: '',
            is_owner: false,
            has_unseen_observer: false,
          },
        })
      );
      // No interactions seeded — the scene is empty at load.

      renderWithProviders(<GamePage />);

      await screen.findByLabelText('Thread sidebar');

      store.dispatch(
        addSceneInteraction({
          character: ACTIVE_NAME,
          interaction: {
            id: 1,
            persona: { id: 42, name: 'Mysterious Stranger', thumbnail_url: '' },
            content: 'psst -- a word, in private.',
            mode: 'whisper',
            timestamp: '2026-01-01T00:00:01Z',
            scene_id: 200,
            place_id: null,
            place_name: null,
            receiver_persona_ids: [7],
            target_persona_ids: [],
          },
        })
      );

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperButton = () =>
        within(sidebar)
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;

      await waitFor(() => {
        expect(within(whisperButton()).getByText('1')).toBeInTheDocument();
      });
    });

    it('falls back to the plain ChatWindow with no thread sidebar when there is no active scene', () => {
      store.dispatch(setAccount(mockAccount));
      store.dispatch(startSession(ACTIVE_NAME));

      renderWithProviders(<GamePage />);

      expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
      expect(screen.queryByLabelText('Thread sidebar')).not.toBeInTheDocument();
      expect(screen.queryByTestId('pose-unit')).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Scene toolset on /game + live tabletalk (#2156 Task 6)
  // ---------------------------------------------------------------------------

  describe('scene toolset', () => {
    beforeEach(() => {
      mockFetchPlaces.mockClear();
      mockFetchPlaces.mockResolvedValue({ results: [] });
    });

    it('renders ConsentPrompt/PlaceBar/ActionPanel/PendingActionAttachments when a scene is active', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithRoom();

      renderWithProviders(<GamePage />);

      expect(await screen.findByTestId('consent-prompt')).toBeInTheDocument();
      expect(screen.getByTestId('place-bar')).toBeInTheDocument();
      expect(screen.getByTestId('action-panel')).toBeInTheDocument();
      expect(screen.getByTestId('pending-action-attachments')).toBeInTheDocument();
    });

    it('does not render the scene toolset when there is no active scene', () => {
      store.dispatch(setAccount(mockAccount));
      store.dispatch(startSession(ACTIVE_NAME));

      renderWithProviders(<GamePage />);

      expect(screen.queryByTestId('consent-prompt')).not.toBeInTheDocument();
      expect(screen.queryByTestId('place-bar')).not.toBeInTheDocument();
      expect(screen.queryByTestId('action-panel')).not.toBeInTheDocument();
      expect(screen.queryByTestId('pending-action-attachments')).not.toBeInTheDocument();
    });

    it('passes isAtPlace=true to ModeSelector, offering the tt mode, when a place has viewer_is_present:true', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithRoom();
      mockFetchPlaces.mockResolvedValue({
        results: [{ id: 9, name: 'The Fountain', description: '', viewer_is_present: true }],
      });

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);

      const trigger = await screen.findByRole('button', { name: 'Pose' });
      await user.click(trigger);

      expect(await screen.findByText('Tabletalk')).toBeInTheDocument();
    });

    it('does not offer the tt mode when the viewer is not present at any place', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithRoom();
      mockFetchPlaces.mockResolvedValue({
        results: [{ id: 9, name: 'The Fountain', description: '', viewer_is_present: false }],
      });

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);

      const trigger = await screen.findByRole('button', { name: 'Pose' });
      await user.click(trigger);

      expect(screen.queryByText('Tabletalk')).not.toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // Conversation tabs (#2165): sidebar-click opens/focuses a tab; the tab
  // strip narrows the feed + locks the composer; close falls back to the
  // room anchor; a scene change clears every open tab.
  // ---------------------------------------------------------------------------

  describe('conversation tabs (#2165)', () => {
    it('sidebar whisper click opens a tab, narrows feed, locks composer to it', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);

      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperRow = within(sidebar)
        .getByText(/whisper/i)
        .closest('button') as HTMLElement;
      await user.click(whisperRow);

      // A tablist appears with the room anchor + the whisper tab, the
      // whisper tab selected.
      const tablist = await screen.findByRole('tablist', { name: 'Conversations' });
      const tabs = within(tablist).getAllByRole('tab');
      expect(tabs).toHaveLength(2);
      const whisperTab = within(tablist)
        .getByText(/whisper/i)
        .closest('[role="tab"]') as HTMLElement;
      expect(whisperTab).toHaveAttribute('aria-selected', 'true');
      const roomTab = within(tablist)
        .getByText('The Grand Ballroom')
        .closest('[role="tab"]') as HTMLElement;
      expect(roomTab).toHaveAttribute('aria-selected', 'false');

      // The feed narrows to ONLY the whisper thread's interactions.
      expect(screen.queryByText('stretches languidly.')).not.toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();

      // The composer is locked to the whisper audience.
      const lockedMode = screen.getByTitle('Audience is locked to this conversation tab');
      expect(lockedMode).toHaveTextContent(/whisper/i);
      expect(screen.queryByRole('button', { name: 'Pose' })).not.toBeInTheDocument();
    });

    it('clicking room anchor tab restores full feed, re-enables mode dropdown', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);

      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperRow = within(sidebar)
        .getByText(/whisper/i)
        .closest('button') as HTMLElement;
      await user.click(whisperRow);

      const tablist = await screen.findByRole('tablist', { name: 'Conversations' });
      const roomTab = within(tablist)
        .getByText('The Grand Ballroom')
        .closest('[role="tab"]') as HTMLElement;
      await user.click(roomTab);

      // Full feed is back.
      expect(await screen.findByText('stretches languidly.')).toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();

      // The mode dropdown is re-enabled (unlocked) — the trigger button
      // renders instead of the locked static label.
      expect(await screen.findByRole('button', { name: 'Pose' })).toBeInTheDocument();
      expect(
        screen.queryByTitle('Audience is locked to this conversation tab')
      ).not.toBeInTheDocument();

      // The tab strip still shows both tabs — closing wasn't involved — with
      // the room anchor now selected.
      expect(roomTab).toHaveAttribute('aria-selected', 'true');
    });

    it('badges whisper tab unread while room anchor active, clears on switch', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);
      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperRow = () =>
        within(sidebar)
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;
      const roomRow = () =>
        within(sidebar).getByText('The Grand Ballroom').closest('button') as HTMLElement;

      // Open the whisper tab, then focus back on the room anchor — the tab
      // stays open (only closing removes it from openThreadTabs).
      await user.click(whisperRow());
      await screen.findByRole('tablist', { name: 'Conversations' });
      await user.click(roomRow());

      // A new whisper arrives, in the same thread, from someone else, while
      // the room anchor is active.
      store.dispatch(
        addSceneInteraction({
          character: ACTIVE_NAME,
          interaction: {
            id: 3,
            persona: { id: 9, name: 'Bystander', thumbnail_url: '' },
            content: 'psst, did you hear?',
            mode: 'whisper',
            timestamp: '2026-01-01T00:02:00Z',
            scene_id: 100,
            place_id: null,
            place_name: null,
            receiver_persona_ids: [7],
            target_persona_ids: [],
          },
        })
      );

      const tablist = screen.getByRole('tablist', { name: 'Conversations' });
      const whisperTab = () =>
        within(tablist)
          .getByText(/whisper/i)
          .closest('[role="tab"]') as HTMLElement;

      await waitFor(() => {
        expect(within(whisperTab()).getByText('1')).toBeInTheDocument();
      });

      // Switching to the whisper tab clears its badge.
      await user.click(whisperTab());
      await waitFor(() => {
        expect(within(whisperTab()).queryByText(/^[1-9]/)).not.toBeInTheDocument();
      });
    });

    it('closing the active tab falls back to room anchor; sidebar reopens it', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);
      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperRow = () =>
        within(sidebar)
          .getByText(/whisper/i)
          .closest('button') as HTMLElement;

      await user.click(whisperRow());
      const tablist = await screen.findByRole('tablist', { name: 'Conversations' });
      const closeButton = within(tablist).getByRole('button', { name: /close whisper/i });
      await user.click(closeButton);

      // The strip disappears entirely (no open tabs left).
      expect(screen.queryByRole('tablist', { name: 'Conversations' })).not.toBeInTheDocument();

      // The room anchor is active again — full feed is back.
      expect(screen.getByText('stretches languidly.')).toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();

      // Clicking the sidebar thread again reopens the tab.
      await user.click(whisperRow());
      expect(await screen.findByRole('tablist', { name: 'Conversations' })).toBeInTheDocument();
    });

    it('clears the tab strip when the active puppet moves into a new scene', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);
      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperRow = within(sidebar)
        .getByText(/whisper/i)
        .closest('button') as HTMLElement;
      await user.click(whisperRow);
      await screen.findByRole('tablist', { name: 'Conversations' });

      store.dispatch(
        setSessionScene({
          character: ACTIVE_NAME,
          scene: {
            id: 300,
            name: 'The Garden',
            description: '',
            is_owner: false,
            has_unseen_observer: false,
          },
        })
      );

      await waitFor(() => {
        expect(screen.queryByRole('tablist', { name: 'Conversations' })).not.toBeInTheDocument();
      });
    });

    it('sidebar All button restores the room feed while a whisper tab is active', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();
      seedWhisperThread();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);
      await screen.findByText('stretches languidly.');

      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperRow = within(sidebar)
        .getByText(/whisper/i)
        .closest('button') as HTMLElement;
      await user.click(whisperRow);
      await screen.findByRole('tablist', { name: 'Conversations' });

      // Feed is narrowed to the whisper thread only.
      expect(screen.queryByText('stretches languidly.')).not.toBeInTheDocument();

      // Clicking the sidebar's "All" button (#2165 review fix) must restore
      // the room feed AND re-anchor the tab strip to the room tab —
      // `threading.showAll()` alone only resets the filter/mute state, not
      // the active conversation tab.
      const allButton = within(sidebar).getByRole('button', { name: 'All' });
      await user.click(allButton);

      expect(await screen.findByText('stretches languidly.')).toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();

      const tablist = screen.getByRole('tablist', { name: 'Conversations' });
      const roomTab = within(tablist)
        .getByText('The Grand Ballroom')
        .closest('[role="tab"]') as HTMLElement;
      expect(roomTab).toHaveAttribute('aria-selected', 'true');
    });

    it('room tab click resets a stale composer mode left by a drawer whisper', async () => {
      store.dispatch(setAccount(mockAccount));
      seedActiveSceneWithPose();

      const user = userEvent.setup();
      renderWithProviders(<GamePage />);
      await screen.findByText('stretches languidly.');

      // Drawer-whisper (#2156): clicking the pose's avatar opens the
      // character card; "Whisper" sets an UNLOCKED composer mode targeting
      // the persona, before any conversation tab exists.
      await user.click(screen.getByRole('button', { name: `View ${ACTIVE_NAME}` }));
      await user.click(await screen.findByRole('button', { name: 'Whisper' }));
      expect(screen.getByText(`Whisper → ${ACTIVE_NAME}`)).toBeInTheDocument();

      // Open and activate a real conversation tab.
      seedWhisperThread();
      const sidebar = screen.getByLabelText('Thread sidebar');
      const whisperRow = await within(sidebar).findByText(/whisper/i);
      await user.click(whisperRow.closest('button') as HTMLElement);
      const tablist = await screen.findByRole('tablist', { name: 'Conversations' });

      // Clicking the strip's room tab (#2165 review fix) must reset the
      // composer to the room pose mode — not leave the stale drawer-whisper
      // mode that predates any tab.
      const roomTab = within(tablist)
        .getByText('The Grand Ballroom')
        .closest('[role="tab"]') as HTMLElement;
      await user.click(roomTab);

      expect(await screen.findByRole('button', { name: 'Pose' })).toBeInTheDocument();
      expect(screen.getByText('Pose → The Grand Ballroom')).toBeInTheDocument();
      expect(screen.queryByText(`Whisper → ${ACTIVE_NAME}`)).not.toBeInTheDocument();
    });
  });
});
