import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, vi, beforeEach, afterEach, expect } from 'vitest';
import { GamePage } from './GamePage';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { mockAccount } from '@/test/mocks/account';
import { startSession, setSessionScene, addSceneInteraction, resetGame } from '@/store/gameSlice';
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

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [rosterEntry],
    isLoading: false,
    isError: false,
  })),
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
  };
});

// PoseUnit → PersonaContextMenu pulls in combat/queries for the duel-challenge
// affordance; mirrors PoseUnit.test.tsx's mock to keep it from firing real fetches.
vi.mock('@/combat/queries', () => ({
  useOutcomeDetails: vi.fn().mockReturnValue({ data: [], isLoading: false }),
  useDispatchPlayerAction: vi.fn().mockReturnValue({ mutateAsync: vi.fn(), isPending: false }),
  combatKeys: { duelChallengesAll: () => ['combat', 'duel-challenges'] },
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

      // Clicking the whisper thread must narrow the feed to just that thread —
      // the room pose disappears and the whisper stays (GamePage's
      // handleThreadClick must call toggleThreadVisibility, not just
      // setSelectedThread, or filteredInteractions never changes).
      expect(screen.queryByText('stretches languidly.')).not.toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();

      // "All" restores both threads.
      await user.click(within(sidebar).getByText('All'));
      expect(screen.getByText('stretches languidly.')).toBeInTheDocument();
      expect(screen.getByText('meet me by the fountain at midnight.')).toBeInTheDocument();
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
});
