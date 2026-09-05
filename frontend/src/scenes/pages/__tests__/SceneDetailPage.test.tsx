/**
 * SceneDetailPage smoke test
 *
 * Verifies that SineatingInbox and SoulTetherRescuePrompt are mounted on the
 * scene detail page alongside ConsentPrompt when a scene is active.
 *
 * Heavily mocks scene queries, action queries, and magic queries so this test
 * doesn't require a live backend. The new components are self-fetching; when
 * no offers exist they return null, so this test asserts they are attempted
 * (i.e., their query hooks are called) rather than asserting DOM presence.
 *
 * Pattern: mocks modelled after StoryDetailPage.test.tsx.
 */

import type { ReactNode } from 'react';
import { Routes, Route, MemoryRouter, useNavigate } from 'react-router-dom';
import { describe, it, vi, beforeEach, expect } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Provider } from 'react-redux';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { SceneDetailPage } from '../SceneDetailPage';
import { fetchPlaces } from '../../actionQueries';

// ---------------------------------------------------------------------------
// Mock scene queries
// ---------------------------------------------------------------------------

// Mutable so individual tests can override the scene detail payload (e.g. to
// set `location`) while keeping the default shape for the other tests.
let mockSceneData: Record<string, unknown> = {
  id: '1',
  name: 'Test Scene',
  is_active: true,
  description: '',
};

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    // SceneDetailPage makes two direct useQuery calls: the scene detail query
    // (queryKey ['scene', id]) and the places-room-id derived query (queryKey
    // ['scene-places', placesRoomId]). Route by queryKey so the second call
    // actually invokes its queryFn (calling the mocked fetchPlaces) instead of
    // returning a fixed canned value regardless of arguments.
    useQuery: vi.fn(
      (config: { queryKey: readonly unknown[]; queryFn?: () => unknown; enabled?: boolean }) => {
        if (config.queryKey[0] === 'scene') {
          return { data: mockSceneData, isLoading: false, refetch: vi.fn() };
        }
        if (config.enabled !== false) {
          config.queryFn?.();
        }
        return { data: undefined, isLoading: false, refetch: vi.fn() };
      }
    ),
    useMutation: vi.fn(() => ({
      mutate: vi.fn(),
      isPending: false,
    })),
    useQueryClient: vi.fn(() => ({
      invalidateQueries: vi.fn(),
    })),
  };
});

// ---------------------------------------------------------------------------
// Mock action queries (used by ConsentPrompt + ActionPanel)
// ---------------------------------------------------------------------------

vi.mock('../../actionQueries', async () => {
  const { useQuery } = await import('@tanstack/react-query');
  const fetchAvailableActions = vi.fn(() =>
    Promise.resolve({ count: 0, next: null, previous: null, results: [] })
  );
  return {
    fetchPendingRequests: vi.fn(() =>
      Promise.resolve({ count: 0, next: null, previous: null, results: [] })
    ),
    createActionRequest: vi.fn(),
    respondToRequest: vi.fn(),
    fetchActionPanelData: vi.fn(() => Promise.resolve({ techniques: [], pending_requests: [] })),
    fetchPlaces: vi.fn(() => Promise.resolve({ results: [] })),
    // Tavern games (#3292): TavernGameWidget mounts alongside PlaceBar and
    // pulls these in - empty results so it renders nothing in this suite,
    // which isn't exercising the coin-stakes widget itself.
    fetchTavernGames: vi.fn(() => Promise.resolve({ results: [] })),
    fetchTavernGameSessions: vi.fn(() => Promise.resolve({ results: [] })),
    openTavernGameSession: vi.fn(),
    joinTavernGameSession: vi.fn(),
    rollTavernGameSession: vi.fn(),
    leaveTavernGameSession: vi.fn(),
    fetchAvailableActions,
    useAvailableActionsQuery: (
      characterId: number | null,
      options: { enabled?: boolean; staleTime?: number; refetchInterval?: number } = {}
    ) =>
      useQuery({
        queryKey: ['available-actions', characterId ?? 0],
        queryFn: () => fetchAvailableActions(),
        enabled: (options.enabled ?? true) && characterId !== null && characterId > 0,
        staleTime: options.staleTime ?? 10_000,
        refetchInterval: options.refetchInterval,
      }),
  };
});

// ---------------------------------------------------------------------------
// Mock roster queries — SceneDetailPage uses useMyRosterEntriesQuery to
// resolve the active persona for Phase 10's pending-action-attachment chip
// strip. The global useQuery mock above returns Scene data for every query,
// so we override the roster hook explicitly to return an array.
// ---------------------------------------------------------------------------

const mockUseMyRosterEntriesQuery = vi.fn(
  (): { data: unknown[]; isLoading: boolean; isError: boolean } => ({
    data: [],
    isLoading: false,
    isError: false,
  })
);

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => mockUseMyRosterEntriesQuery(),
  // The character-card drawer (#2156 Task 7) always mounts (persona is null
  // unless an avatar was clicked) and calls these — stub them out since this
  // test suite isn't exercising the drawer's own identity resolution.
  useRosterEntryByNameQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
  useRosterEntryQuery: vi.fn(() => ({ data: undefined, isLoading: false })),
}));

// ---------------------------------------------------------------------------
// Mock battles queries — SceneDetailPage calls useBattleForSceneQuery to show
// a Battle Writeup link when a battle exists for the scene (#1735).
// ---------------------------------------------------------------------------

const mockUseBattleForSceneQuery = vi.fn(
  (): {
    data: { id: number; outcome: string } | null;
    isLoading: boolean;
    isError: boolean;
  } => ({
    data: null,
    isLoading: false,
    isError: false,
  })
);

vi.mock('@/battles/queries', () => ({
  useBattleForSceneQuery: () => mockUseBattleForSceneQuery(),
}));

// ---------------------------------------------------------------------------
// Mock combat queries/CombatRail — the combat-rail fold-in (#2197). Default:
// no active encounter, so the page stays single-column with no rail.
// ---------------------------------------------------------------------------

const mockUseEncounterForScene = vi.fn(
  (): {
    data: { id: number } | null | undefined;
    isLoading: boolean;
    isError: boolean;
  } => ({
    data: null,
    isLoading: false,
    isError: false,
  })
);

// GMEncounterControls' gate reads useCombatEncounter's full detail (is_gm) —
// stub it too (default: no data) so it never falls through to the real
// useQuery mock above, which eagerly calls any non-'scene' queryFn for real
// (an uncaught /api/combat/<id>/ fetch that jsdom can't resolve, #3067).
const mockUseCombatEncounter = vi.fn((): { data: { id: number; is_gm: boolean } | undefined } => ({
  data: undefined,
}));

vi.mock('@/combat/queries', async (importOriginal) => {
  // SceneTacticalMap (rendered in the header) also pulls real hooks (e.g.
  // useDispatchPlayerAction) from this module — preserve everything else and
  // only override useEncounterForScene/useCombatEncounter.
  const actual = await importOriginal<typeof import('@/combat/queries')>();
  return {
    ...actual,
    useEncounterForScene: () => mockUseEncounterForScene(),
    useCombatEncounter: () => mockUseCombatEncounter(),
  };
});

vi.mock('@/combat/components/CombatRail', () => ({
  CombatRail: ({
    sceneId,
    encounterId,
    onDismissOutcome,
  }: {
    sceneId: number;
    encounterId: number;
    onDismissOutcome?: () => void;
  }) => (
    <div data-testid="combat-rail-stub" data-scene-id={sceneId} data-encounter-id={encounterId}>
      CombatRail [{encounterId}]
      {onDismissOutcome && (
        <button type="button" data-testid="combat-rail-dismiss-stub" onClick={onDismissOutcome}>
          Dismiss
        </button>
      )}
    </div>
  ),
}));

// GMEncounterControls (#3067) calls useCombatEncounter directly (real fetch) —
// stub it out here the same way CombatRail is stubbed above, so this page
// test doesn't need to mock @/combat/queries' useCombatEncounter too.
vi.mock('@/combat/sections/GMEncounterControls', () => ({
  GMEncounterControls: ({
    sceneId,
    encounter,
    viewerCanGm,
  }: {
    sceneId: number;
    encounter: { id: number } | null;
    viewerCanGm: boolean;
  }) => (
    <div
      data-testid="gm-encounter-controls-stub"
      data-scene-id={sceneId}
      data-encounter-id={encounter?.id ?? 'none'}
      data-viewer-can-gm={String(viewerCanGm)}
    >
      GMEncounterControls
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock pending-unlinked-actions hook — Phase 10's chip strip queries this.
// ---------------------------------------------------------------------------

vi.mock('../../hooks/usePendingUnlinkedActions', () => ({
  usePendingUnlinkedActions: vi.fn(() => ({
    data: [],
    isLoading: false,
    isError: false,
  })),
}));

// ---------------------------------------------------------------------------
// Mock magic queries — both inbox components self-fetch with these hooks
// ---------------------------------------------------------------------------

const mockUsePendingSineatingOffers = vi.fn(() => ({
  data: { count: 0, next: null, previous: null, results: [] },
  isLoading: false,
  isError: false,
}));

const mockUsePendingStageAdvanceOffers = vi.fn(() => ({
  data: { count: 0, next: null, previous: null, results: [] },
  isLoading: false,
  isError: false,
}));

vi.mock('@/magic/queries', () => ({
  usePendingSineatingOffers: () => mockUsePendingSineatingOffers(),
  usePendingStageAdvanceOffers: () => mockUsePendingStageAdvanceOffers(),
  useRespondToSineating: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useRespondToStageAdvance: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  usePendingEntryFlourishOffers: () => ({ data: { results: [] } }),
  useRespondToEntryFlourish: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCharacterResonances: vi.fn(() => ({ data: [], isLoading: false })),
}));

// SelfCheckPanel + CheckCallPromptCard (#3295) self-fetching queries — same
// "mock the query module so the real fetch never fires" pattern as every
// other panel query module in this file (jsdom's fetch cannot resolve a
// relative URL, so an unmocked queryFn crashes any test that reaches it).
vi.mock('@/checks/queries', () => ({
  usePlayerCheckTypeCatalog: vi.fn(() => ({ data: [] })),
  useMyCheckCalls: vi.fn(() => ({ data: [] })),
}));

// ---------------------------------------------------------------------------
// Mock redux selectors (game.active character + auth.account)
// ---------------------------------------------------------------------------

// Mutable so #3412 S4's speakingAs tests can drive `state.game.active`
// without a real store — every other test relies on the null default.
let mockGameActive: string | null = null;

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({
      game: { active: mockGameActive },
      auth: {
        account: {
          id: 1,
          username: 'testuser',
          available_characters: [],
        },
      },
    })
  ),
  useAccount: vi.fn(() => ({
    id: 1,
    username: 'testuser',
    available_characters: [],
  })),
}));

// Mock react-redux useSelector used by SineatingInbox and SoulTetherRescuePrompt
vi.mock('react-redux', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-redux')>();
  return {
    ...actual,
    useSelector: vi.fn((selector: (state: unknown) => unknown) =>
      selector({
        auth: {
          account: {
            id: 1,
            username: 'testuser',
            available_characters: [],
          },
        },
      })
    ),
  };
});

// ---------------------------------------------------------------------------
// Mock sub-components that have heavy deps
// ---------------------------------------------------------------------------

vi.mock('../../components/SceneHeader', () => ({
  SceneHeader: () => <div data-testid="scene-header">SceneHeader</div>,
}));

vi.mock('../../components/SceneInteractionPanel', () => ({
  SceneInteractionPanel: () => (
    <div data-testid="scene-interaction-panel">SceneInteractionPanel</div>
  ),
}));

// #3565 - ScenarioCard is self-fetching (useSceneScenarioQuery); this smoke
// test's generic useQuery mock invokes any enabled queryFn for real, which
// would fire a live `fetch()` against a relative URL and reject. Stub it out
// like the other self-fetching page components below.
vi.mock('../../components/ScenarioCard', () => ({
  ScenarioCard: () => <div data-testid="scenario-card">ScenarioCard</div>,
}));

vi.mock('../../components/ActionPanel', () => ({
  ActionPanel: () => <div data-testid="action-panel">ActionPanel</div>,
}));

vi.mock('../../components/PlaceBar', () => ({
  PlaceBar: () => <div data-testid="place-bar">PlaceBar</div>,
}));

vi.mock('../../components/SpeakerQueueBar', () => ({
  SpeakerQueueBar: () => <div data-testid="speaker-queue-bar">SpeakerQueueBar</div>,
}));

vi.mock('../../components/ConsentPrompt', () => ({
  ConsentPrompt: () => <div data-testid="consent-prompt">ConsentPrompt</div>,
}));

vi.mock('@/boundaries/components/SceneLinesAndVeilsCard', () => ({
  SceneLinesAndVeilsCard: () => (
    <div data-testid="lines-and-veils-card">SceneLinesAndVeilsCard</div>
  ),
}));

vi.mock('../../components/HighlightReel', () => ({
  HighlightReel: () => <div data-testid="highlight-reel">HighlightReel</div>,
}));

vi.mock('@/rituals/components/RitualProposedChip', () => ({
  RitualProposedChip: () => <div data-testid="ritual-proposed-chip">RitualProposedChip</div>,
}));

// #2075: LinkedStoriesPanel calls apiFetch for episode-scenes; mock the crossover
// module so the scene test doesn't hit real fetch.
vi.mock('@/crossover/components/LinkedStoriesPanel', () => ({
  LinkedStoriesPanel: () => <div data-testid="linked-stories-panel" />,
}));

// Captures the props each render passes so #3412 S4's speakingAs assertion
// can inspect them without deep-rendering the real composer.
const mockCommandInput = vi.fn();
vi.mock('@/game/components/CommandInput', () => ({
  CommandInput: (props: unknown) => {
    mockCommandInput(props);
    return <div data-testid="command-input">CommandInput</div>;
  },
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SceneDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSceneData = {
      id: '1',
      name: 'Test Scene',
      is_active: true,
      description: '',
    };
    // Reset battle query to default (no battle) by default.
    mockUseBattleForSceneQuery.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });
    // Reset encounter query to default (no active encounter) by default.
    mockUseEncounterForScene.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });
    mockUseCombatEncounter.mockReturnValue({ data: undefined });
    // Reset roster entries to default (empty) by default.
    mockUseMyRosterEntriesQuery.mockReturnValue({ data: [], isLoading: false, isError: false });
    // Reset the mocked game.active selector to default (no active character).
    mockGameActive = null;
  });

  it('renders without crashing', () => {
    const { container } = renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    expect(container.firstChild).not.toBeNull();
  });

  it('queries pending sineating offers (SineatingInbox is mounted)', () => {
    renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    // If the hook was called, the inbox component is mounted
    expect(mockUsePendingSineatingOffers).toHaveBeenCalled();
  });

  it('queries pending stage-advance offers (SoulTetherRescuePrompt is mounted)', () => {
    renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    // If the hook was called, the rescue prompt is mounted
    expect(mockUsePendingStageAdvanceOffers).toHaveBeenCalled();
  });

  it('fetches places by the scene’s room id, not the scene id (fold-in fix, #2156)', () => {
    // The route/scene id is '5', but the scene's location (room) is 777 —
    // fetchPlaces filters ?room=<id>, so it must be called with the room id.
    mockSceneData = {
      id: '5',
      name: 'Test Scene',
      is_active: true,
      description: '',
      location: { id: 777, name: 'The Hall' },
    };

    renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/5'] }
    );

    expect(fetchPlaces).toHaveBeenCalledWith('777');
  });

  it('shows a Battle Writeup link when a concluded battle exists for the scene (#1735)', () => {
    mockUseBattleForSceneQuery.mockReturnValue({
      data: { id: 42, outcome: 'attacker_decisive' },
      isLoading: false,
      isError: false,
    });

    const { getByTestId } = renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    const link = getByTestId('scene-battle-writeup-link');
    expect(link).toHaveAttribute('href', '/battles/42');
    expect(link).toHaveTextContent('Battle Writeup');
  });

  it('does not show a Battle Writeup link when no battle exists (#1735)', () => {
    const { queryByTestId } = renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    expect(queryByTestId('scene-battle-writeup-link')).not.toBeInTheDocument();
  });

  it('links to the live battle map, not the writeup, while the battle is unresolved (#2157)', () => {
    mockUseBattleForSceneQuery.mockReturnValue({
      data: { id: 42, outcome: 'unresolved' },
      isLoading: false,
      isError: false,
    });

    const { getByTestId, queryByTestId } = renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    const link = getByTestId('scene-battle-map-link');
    expect(link).toHaveAttribute('href', '/scenes/1/battle');
    expect(link).toHaveTextContent('Battle Map');
    expect(queryByTestId('scene-battle-writeup-link')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Combat rail fold-in (#2197) — CombatRail renders in-scene instead of a
  // dedicated /scenes/:id/combat route.
  // -------------------------------------------------------------------------

  it('renders CombatRail when the scene has an active encounter (#2197)', () => {
    mockUseEncounterForScene.mockReturnValue({
      data: { id: 7 },
      isLoading: false,
      isError: false,
    });

    const { getByTestId } = renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    const rail = getByTestId('combat-rail-stub');
    expect(rail).toBeInTheDocument();
    expect(rail).toHaveAttribute('data-encounter-id', '7');
    expect(rail).toHaveAttribute('data-scene-id', '1');
  });

  it('does not render CombatRail when there is no active encounter (#2197)', () => {
    mockUseEncounterForScene.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });

    const { queryByTestId } = renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    expect(queryByTestId('combat-rail-stub')).not.toBeInTheDocument();
  });

  it('keeps CombatRail mounted on the lingering encounter id until dismissed (#3551)', () => {
    mockUseEncounterForScene.mockReturnValue({
      data: { id: 7 },
      isLoading: false,
      isError: false,
    });

    // renderWithProviders' own rerender re-renders a bare element with no
    // providers, which would unmount+remount the whole tree and lose the
    // page's lingering-encounter state, so this keeps one stable provider tree
    // across both render calls (same pattern as Compass.test.tsx).
    const queryClient = new QueryClient();
    function wrap(ui: ReactNode) {
      return (
        <Provider store={store}>
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={['/scenes/1']}>{ui}</MemoryRouter>
          </QueryClientProvider>
        </Provider>
      );
    }
    const page = (
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>
    );

    const { getByTestId, queryByTestId, rerender } = render(wrap(page));

    expect(getByTestId('combat-rail-stub')).toHaveAttribute('data-encounter-id', '7');

    // The list poll drops the completed encounter from useEncounterForScene.
    mockUseEncounterForScene.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });
    rerender(wrap(page));

    const lingeringRail = getByTestId('combat-rail-stub');
    expect(lingeringRail).toHaveAttribute('data-encounter-id', '7');

    fireEvent.click(getByTestId('combat-rail-dismiss-stub'));

    expect(queryByTestId('combat-rail-stub')).not.toBeInTheDocument();
  });

  it('hides the rail immediately on dismiss, before the list poll drops the encounter (#3551 minor 4)', () => {
    mockUseEncounterForScene.mockReturnValue({
      data: { id: 7 },
      isLoading: false,
      isError: false,
    });

    const { getByTestId, queryByTestId } = renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    expect(getByTestId('combat-rail-stub')).toHaveAttribute('data-encounter-id', '7');

    // Dismiss before useEncounterForScene's own poll has dropped the completed
    // encounter, so hasActiveEncounter is still true at click time.
    fireEvent.click(getByTestId('combat-rail-dismiss-stub'));

    expect(queryByTestId('combat-rail-stub')).not.toBeInTheDocument();
  });

  it('hides rail-side GM controls once the encounter completes, but keeps the rail lingering (#3551 important 2)', () => {
    mockUseEncounterForScene.mockReturnValue({
      data: { id: 7 },
      isLoading: false,
      isError: false,
    });
    mockUseCombatEncounter.mockReturnValue({ data: { id: 7, is_gm: true } });

    const queryClient = new QueryClient();
    function wrap(ui: ReactNode) {
      return (
        <Provider store={store}>
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={['/scenes/1']}>{ui}</MemoryRouter>
          </QueryClientProvider>
        </Provider>
      );
    }
    // A fresh <Routes>/<Route> element each call (not one `page` const reused
    // for both render calls): react-router's useRoutes memoizes its rendered
    // match on `children` identity, so reusing the same element reference
    // across a rerender would silently skip SceneDetailPage's re-render
    // entirely, so the mocked hook update below would never be observed.
    function makePage() {
      return (
        <Routes>
          <Route path="/scenes/:id" element={<SceneDetailPage />} />
        </Routes>
      );
    }

    const { getByTestId, rerender } = render(wrap(makePage()));

    const railBefore = getByTestId('scene-detail-combat-rail');
    expect(within(railBefore).getByTestId('gm-encounter-controls-stub')).toBeInTheDocument();
    expect(getByTestId('combat-rail-stub')).toHaveAttribute('data-encounter-id', '7');

    // The list poll drops the completed encounter (the rail lingers, previous
    // test) but the GM lifecycle controls (add-opponent/settings) must not,
    // since the backend has no COMPLETED guard on those actions. (The header's
    // own "Start Encounter" GMEncounterControls now appears too and shares the
    // same stub test id, so the assertion below is scoped to the rail column.)
    mockUseEncounterForScene.mockReturnValue({
      data: null,
      isLoading: false,
      isError: false,
    });
    rerender(wrap(makePage()));

    const railAfter = getByTestId('scene-detail-combat-rail');
    expect(within(railAfter).queryByTestId('gm-encounter-controls-stub')).not.toBeInTheDocument();
    expect(getByTestId('combat-rail-stub')).toHaveAttribute('data-encounter-id', '7');
  });

  it('resets the lingering rail when the scene id changes (#3551 important 1)', () => {
    mockUseEncounterForScene.mockReturnValue({
      data: { id: 7 },
      isLoading: false,
      isError: false,
    });

    function NavigateToScene2() {
      const navigate = useNavigate();
      return (
        <button type="button" data-testid="nav-to-scene-2" onClick={() => navigate('/scenes/2')}>
          Go to scene 2
        </button>
      );
    }

    const { getByTestId, queryByTestId } = render(
      <Provider store={store}>
        <QueryClientProvider client={new QueryClient()}>
          <MemoryRouter initialEntries={['/scenes/1']}>
            <NavigateToScene2 />
            <Routes>
              <Route path="/scenes/:id" element={<SceneDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </Provider>
    );

    expect(getByTestId('combat-rail-stub')).toHaveAttribute('data-encounter-id', '7');

    // Scene 1's fight completed and the poll already dropped it before the
    // player navigates away, so scene 1's rail is lingering at click time.
    mockUseEncounterForScene.mockReturnValue({ data: null, isLoading: false, isError: false });

    fireEvent.click(getByTestId('nav-to-scene-2'));

    // /scenes/:id matches the same Route element on both scenes, so React
    // reuses the SceneDetailPage instance instead of remounting it (#3551), so
    // scene 1's lingering rail must not survive onto scene 2.
    expect(queryByTestId('combat-rail-stub')).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // #3412 S4 — speakingAs threading. SceneDetailPage IS the combat composer
  // now (#2197 folded the standalone CombatScenePage in here, encounter rail
  // included) — this covers the "CombatScenePage passes speakingAs" item for
  // that reason. Shallow: asserts the prop shape CommandInput receives,
  // mirroring GamePage's own construction (activeEntry ? {name,
  // thumbnailUrl} : undefined).
  // -------------------------------------------------------------------------

  it('threads speakingAs to CommandInput from the active roster entry (#3412 S4)', () => {
    mockUseMyRosterEntriesQuery.mockReturnValue({
      data: [
        {
          id: 1,
          name: 'Aria',
          character_id: 42,
          profile_picture_url: 'https://example.com/aria.png',
          primary_persona_id: 7,
          active_persona_id: 7,
          unread_narrative_count: 0,
          lifecycle_state: 'ALIVE',
        },
      ],
      isLoading: false,
      isError: false,
    });
    mockGameActive = 'Aria';

    renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    expect(mockCommandInput).toHaveBeenCalledWith(
      expect.objectContaining({
        speakingAs: { name: 'Aria', thumbnailUrl: 'https://example.com/aria.png' },
      })
    );
  });

  it('omits speakingAs from CommandInput when there is no active roster entry (#3412 S4)', () => {
    mockGameActive = 'Aria';
    // Deliberately leave mockUseMyRosterEntriesQuery at its default empty
    // array — activeEntry resolves to null even though a session is active.

    renderWithProviders(
      <Routes>
        <Route path="/scenes/:id" element={<SceneDetailPage />} />
      </Routes>,
      { initialEntries: ['/scenes/1'] }
    );

    expect(mockCommandInput).toHaveBeenCalledWith(
      expect.objectContaining({ speakingAs: undefined })
    );
  });
});
