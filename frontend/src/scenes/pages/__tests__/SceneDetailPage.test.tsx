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

import { Routes, Route } from 'react-router-dom';
import { describe, it, vi, beforeEach, expect } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SceneDetailPage } from '../SceneDetailPage';

// ---------------------------------------------------------------------------
// Mock scene queries
// ---------------------------------------------------------------------------

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    useQuery: vi.fn(() => ({
      data: {
        id: '1',
        name: 'Test Scene',
        is_active: true,
        description: '',
      },
      isLoading: false,
      refetch: vi.fn(),
    })),
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

vi.mock('../../actionQueries', () => ({
  fetchPendingRequests: vi.fn(() =>
    Promise.resolve({ count: 0, next: null, previous: null, results: [] })
  ),
  createActionRequest: vi.fn(),
  respondToRequest: vi.fn(),
  fetchActionPanelData: vi.fn(() => Promise.resolve({ techniques: [], pending_requests: [] })),
}));

// ---------------------------------------------------------------------------
// Mock roster queries — SceneDetailPage uses useMyRosterEntriesQuery to
// resolve the active persona for Phase 10's pending-action-attachment chip
// strip. The global useQuery mock above returns Scene data for every query,
// so we override the roster hook explicitly to return an array.
// ---------------------------------------------------------------------------

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [],
    isLoading: false,
    isError: false,
  })),
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
}));

// ---------------------------------------------------------------------------
// Mock redux selectors (game.active character + auth.account)
// ---------------------------------------------------------------------------

vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({
      game: { active: null },
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

vi.mock('../../components/ActionPanel', () => ({
  ActionPanel: () => <div data-testid="action-panel">ActionPanel</div>,
}));

vi.mock('../../components/PlaceBar', () => ({
  PlaceBar: () => <div data-testid="place-bar">PlaceBar</div>,
}));

vi.mock('../../components/ConsentPrompt', () => ({
  ConsentPrompt: () => <div data-testid="consent-prompt">ConsentPrompt</div>,
}));

vi.mock('@/game/components/CommandInput', () => ({
  CommandInput: () => <div data-testid="command-input">CommandInput</div>,
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SceneDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
