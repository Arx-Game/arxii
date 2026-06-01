import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { Thread, ThreadHubSummary, CharacterResonance } from '../../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('@/magic/queries', () => ({
  useThread: vi.fn(),
  useThreadHubSummary: vi.fn(),
  useCharacterResonances: vi.fn(),
  useThreads: vi.fn().mockReturnValue({ data: { results: [] } }),
  useCommitPull: vi.fn().mockReturnValue({ mutate: vi.fn(), isPending: false }),
  usePatchThreadNarrative: vi.fn(),
  useRetireThread: vi.fn(),
  useImbueThread: vi.fn(),
  useCrossXPLock: vi.fn(),
}));

vi.mock('@/progression/queries', () => ({
  useAccountProgressionQuery: vi.fn(),
}));

// previewPull is a plain async helper, not a hook
vi.mock('@/magic/api', () => ({
  previewPull: vi.fn().mockResolvedValue({
    resonance_cost: 3,
    anima_cost: 1,
    affordable: true,
    capped_intensity: false,
    resolved_effects: [],
  }),
}));

import * as magicQueries from '@/magic/queries';
import * as progressionQueries from '@/progression/queries';
import { ThreadDetailPage } from '../ThreadDetailPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper(initialPath = '/threads/1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route path="/threads/:id" element={children} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };
}

const makeThread = (overrides: Partial<Thread> = {}): Thread => ({
  id: 1,
  owner: 100,
  resonance: 1,
  resonance_name: 'Bene',
  target_kind: 'RELATIONSHIP_TRACK',
  name: 'Ember Thread',
  description: 'A test description.',
  level: 10,
  developed_points: 25,
  path_cap: 20,
  anchor_cap: 20,
  effective_cap: 20,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
  ...overrides,
});

const makeSummary = (overrides: Partial<ThreadHubSummary> = {}): ThreadHubSummary => ({
  balances: [{ resonance_id: 1, balance: 42, lifetime_earned: 100, flavor_text: '' }],
  ready_thread_ids: [],
  near_xp_lock_thread_ids: [],
  blocked_thread_ids: [],
  weaving_eligibility: {},
  weavable_traits: [],
  weavable_techniques: [],
  room_property_ids: [],
  weavable_relationship_track_ids: [],
  ...overrides,
});

const makeCharacterResonance = (
  overrides: Partial<CharacterResonance> = {}
): CharacterResonance => ({
  id: 10,
  character_sheet: 100,
  resonance: 1,
  resonance_name: 'Bene',
  resonance_detail: {
    id: 1,
    name: 'Bene',
    affinity: 1,
    affinity_name: 'Celestial',
    description: 'A resonance.',
    codex_entry_id: null,
  },
  balance: 42,
  lifetime_earned: 100,
  claimed_at: '2025-01-01T00:00:00Z',
  flavor_text: '',
  ...overrides,
});

type UseQueryReturn<T> = {
  data: T | undefined;
  isLoading: boolean;
  isError: boolean;
  error: null;
};

function makeQueryResult<T>(data: T | undefined, loading = false): UseQueryReturn<T> {
  return { data, isLoading: loading, isError: false, error: null };
}

type MutationState = {
  mutate: ReturnType<typeof vi.fn>;
  isPending: boolean;
  isError: boolean;
  error: Error | null;
  isSuccess: boolean;
};

function makeMutation(overrides: Partial<MutationState> = {}): MutationState {
  return {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
    isSuccess: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockNavigate.mockReset();

  vi.mocked(magicQueries.useThread).mockReturnValue(
    makeQueryResult(makeThread()) as ReturnType<typeof magicQueries.useThread>
  );
  vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
    makeQueryResult(makeSummary()) as ReturnType<typeof magicQueries.useThreadHubSummary>
  );
  vi.mocked(magicQueries.useCharacterResonances).mockReturnValue(
    makeQueryResult([makeCharacterResonance()]) as ReturnType<
      typeof magicQueries.useCharacterResonances
    >
  );
  vi.mocked(magicQueries.usePatchThreadNarrative).mockReturnValue(
    makeMutation() as unknown as ReturnType<typeof magicQueries.usePatchThreadNarrative>
  );
  vi.mocked(magicQueries.useRetireThread).mockReturnValue(
    makeMutation() as unknown as ReturnType<typeof magicQueries.useRetireThread>
  );
  vi.mocked(magicQueries.useImbueThread).mockReturnValue(
    makeMutation() as unknown as ReturnType<typeof magicQueries.useImbueThread>
  );
  vi.mocked(magicQueries.useCrossXPLock).mockReturnValue(
    makeMutation() as unknown as ReturnType<typeof magicQueries.useCrossXPLock>
  );
  vi.mocked(progressionQueries.useAccountProgressionQuery).mockReturnValue(
    makeQueryResult({
      xp: { total_earned: 100, total_spent: 20, current_available: 80 },
      kudos: null,
      xp_transactions: [],
      kudos_transactions: [],
      claim_categories: [],
    }) as ReturnType<typeof progressionQueries.useAccountProgressionQuery>
  );
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ThreadDetailPage', () => {
  it('renders the thread name as heading', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('thread-detail-title')).toHaveTextContent('Ember Thread');
  });

  it('renders the breadcrumb with Threads link', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('link', { name: 'Threads' })).toHaveAttribute('href', '/threads');
  });

  it('renders thread description', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('thread-description')).toHaveTextContent('A test description.');
  });

  it('renders stats card with level and developed points', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('thread-stats-card')).toBeInTheDocument();
    // level 10 / 10 = 1
    expect(screen.getByTestId('thread-stat-level')).toHaveTextContent('1');
    expect(screen.getByTestId('thread-stat-dp')).toHaveTextContent('25');
  });

  it('renders cap fields in stats card', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    // path_cap 20 / 10 = 2
    expect(screen.getByTestId('thread-stat-path-cap')).toHaveTextContent('2');
    // anchor_cap 20 / 10 = 2
    expect(screen.getByTestId('thread-stat-anchor-cap')).toHaveTextContent('2');
    // effective_cap 20 / 10 = 2
    expect(screen.getByTestId('thread-stat-effective-cap')).toHaveTextContent('2');
  });

  it('renders ImbuePanel for non-retired thread below cap', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('imbue-panel')).toBeInTheDocument();
  });

  it('does not render ImbuePanel for retired thread', () => {
    vi.mocked(magicQueries.useThread).mockReturnValue(
      makeQueryResult(makeThread({ retired_at: '2025-06-01T00:00:00Z' })) as ReturnType<
        typeof magicQueries.useThread
      >
    );
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.queryByTestId('imbue-panel')).not.toBeInTheDocument();
  });

  it('renders PullEffectPreview section', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('pull-effect-preview')).toBeInTheDocument();
  });

  it('renders Retire Thread button for non-retired thread', () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('thread-retire-button')).toBeInTheDocument();
  });

  it('does not render Retire Thread button for retired thread', () => {
    vi.mocked(magicQueries.useThread).mockReturnValue(
      makeQueryResult(makeThread({ retired_at: '2025-06-01T00:00:00Z' })) as ReturnType<
        typeof magicQueries.useThread
      >
    );
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.queryByTestId('thread-retire-button')).not.toBeInTheDocument();
  });

  it('opens ThreadRenameDialog when Edit button is clicked', async () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByTestId('thread-edit-button'));
    await waitFor(() => {
      expect(screen.getByTestId('thread-rename-dialog')).toBeInTheDocument();
    });
  });

  it('submits patch through ThreadRenameDialog', async () => {
    const mockMutate = vi.fn().mockImplementation((_vars, opts: { onSuccess?: () => void }) => {
      opts?.onSuccess?.();
    });
    vi.mocked(magicQueries.usePatchThreadNarrative).mockReturnValue(
      makeMutation({ mutate: mockMutate }) as unknown as ReturnType<
        typeof magicQueries.usePatchThreadNarrative
      >
    );

    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByTestId('thread-edit-button'));

    await waitFor(() => {
      expect(screen.getByTestId('thread-rename-dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('thread-rename-submit'));

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledOnce();
    });
  });

  it('opens ThreadRetireDialog when Retire Thread button is clicked', async () => {
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByTestId('thread-retire-button'));
    await waitFor(() => {
      expect(screen.getByTestId('thread-retire-dialog')).toBeInTheDocument();
    });
  });

  it('navigates to /threads after retirement is confirmed', async () => {
    const mockMutate = vi
      .fn()
      .mockImplementation((_id: number, opts: { onSuccess?: () => void }) => {
        opts?.onSuccess?.();
      });
    vi.mocked(magicQueries.useRetireThread).mockReturnValue(
      makeMutation({ mutate: mockMutate }) as unknown as ReturnType<
        typeof magicQueries.useRetireThread
      >
    );

    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByTestId('thread-retire-button'));

    await waitFor(() => {
      expect(screen.getByTestId('thread-retire-dialog')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId('thread-retire-confirm'));

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith(1, expect.any(Object));
      expect(mockNavigate).toHaveBeenCalledWith('/threads');
    });
  });

  it('renders XPLockBoundaryPanel when thread has a near XP lock prospect', () => {
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(
        makeSummary({
          near_xp_lock_thread_ids: [
            { thread_id: 1, boundary_level: 20, xp_cost: 15, dev_points_to_boundary: 5 },
          ],
        })
      ) as ReturnType<typeof magicQueries.useThreadHubSummary>
    );

    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('xp-lock-boundary-panel')).toBeInTheDocument();
  });

  it('shows "not found" when thread data is missing', () => {
    vi.mocked(magicQueries.useThread).mockReturnValue(
      makeQueryResult(undefined) as ReturnType<typeof magicQueries.useThread>
    );
    render(<ThreadDetailPage />, { wrapper: createWrapper() });
    expect(screen.getByText('Thread not found.')).toBeInTheDocument();
  });
});
