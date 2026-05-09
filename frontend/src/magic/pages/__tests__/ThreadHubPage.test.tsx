import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
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
  useThreads: vi.fn(),
  useThreadHubSummary: vi.fn(),
  useCharacterResonances: vi.fn(),
}));

import * as magicQueries from '@/magic/queries';
import { ThreadHubPage } from '../ThreadHubPage';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

const makeThread = (overrides: Partial<Thread> = {}): Thread => ({
  id: 1,
  owner: 100,
  resonance: 1,
  resonance_name: 'Bene',
  target_kind: 'TRAIT',
  name: 'Thread Alpha',
  description: '',
  level: 20,
  developed_points: 40,
  path_cap: 10,
  anchor_cap: 20,
  effective_cap: 10,
  retired_at: null,
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-02T00:00:00Z',
  ...overrides,
});

const makeSummary = (overrides: Partial<ThreadHubSummary> = {}): ThreadHubSummary => ({
  balances: [],
  ready_thread_ids: [],
  near_xp_lock_thread_ids: [],
  blocked_thread_ids: [],
  weaving_eligibility: {},
  ...overrides,
});

const makeCharacterResonance = (
  overrides: Partial<CharacterResonance> = {}
): CharacterResonance => ({
  id: 10,
  character_sheet: 5,
  resonance: 1,
  resonance_name: 'Bene',
  resonance_detail: {
    id: 1,
    name: 'Bene',
    affinity: 1,
    affinity_name: 'Celestial',
    description: 'A celestial resonance.',
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

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  mockNavigate.mockReset();

  vi.mocked(magicQueries.useThreads).mockReturnValue(
    makeQueryResult({ count: 0, next: null, previous: null, results: [] }) as ReturnType<
      typeof magicQueries.useThreads
    >
  );
  vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
    makeQueryResult(makeSummary()) as ReturnType<typeof magicQueries.useThreadHubSummary>
  );
  vi.mocked(magicQueries.useCharacterResonances).mockReturnValue(
    makeQueryResult([]) as ReturnType<typeof magicQueries.useCharacterResonances>
  );
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ThreadHubPage', () => {
  it('renders the page heading', () => {
    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('heading', { name: 'Your Threads' })).toBeInTheDocument();
  });

  it('renders Weave New button(s)', () => {
    render(<ThreadHubPage />, { wrapper: createWrapper() });
    // Header button is always present; empty-state also has one when no threads
    const weaveButtons = screen.getAllByRole('button', { name: 'Weave New' });
    expect(weaveButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('renders Browse Teachers link', () => {
    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('link', { name: 'Browse Teachers' })).toBeInTheDocument();
  });

  it('shows empty state when no threads', () => {
    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByText(/You have no threads yet/)).toBeInTheDocument();
  });

  it('renders resonance balance cards when summary has balances', () => {
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(
        makeSummary({
          balances: [{ resonance_id: 1, balance: 55, lifetime_earned: 120, flavor_text: '' }],
        })
      ) as ReturnType<typeof magicQueries.useThreadHubSummary>
    );
    vi.mocked(magicQueries.useCharacterResonances).mockReturnValue(
      makeQueryResult([makeCharacterResonance()]) as ReturnType<
        typeof magicQueries.useCharacterResonances
      >
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByText('Bene')).toBeInTheDocument();
    expect(screen.getByTestId('resonance-balance-amount')).toHaveTextContent('55');
  });

  it('renders threads grouped by target_kind', () => {
    vi.mocked(magicQueries.useThreads).mockReturnValue(
      makeQueryResult({
        count: 2,
        next: null,
        previous: null,
        results: [
          makeThread({ id: 1, target_kind: 'TRAIT', name: 'Trait Thread' }),
          makeThread({ id: 2, target_kind: 'TECHNIQUE', name: 'Tech Thread' }),
        ],
      }) as ReturnType<typeof magicQueries.useThreads>
    );
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(makeSummary()) as ReturnType<typeof magicQueries.useThreadHubSummary>
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByText('Trait Thread')).toBeInTheDocument();
    expect(screen.getByText('Tech Thread')).toBeInTheDocument();
    // "TRAIT" appears as both the section heading and the badge in ThreadCard — use getAllByText
    expect(screen.getAllByText('TRAIT').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('TECHNIQUE').length).toBeGreaterThanOrEqual(1);
  });

  it('shows ready badge for a thread in ready_thread_ids', () => {
    vi.mocked(magicQueries.useThreads).mockReturnValue(
      makeQueryResult({
        count: 1,
        next: null,
        previous: null,
        results: [makeThread({ id: 10 })],
      }) as ReturnType<typeof magicQueries.useThreads>
    );
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(makeSummary({ ready_thread_ids: [10] })) as ReturnType<
        typeof magicQueries.useThreadHubSummary
      >
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('thread-state-badge-ready')).toBeInTheDocument();
  });

  it('shows near_xp_lock badge for a thread in near_xp_lock_thread_ids', () => {
    vi.mocked(magicQueries.useThreads).mockReturnValue(
      makeQueryResult({
        count: 1,
        next: null,
        previous: null,
        results: [makeThread({ id: 11 })],
      }) as ReturnType<typeof magicQueries.useThreads>
    );
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(
        makeSummary({
          near_xp_lock_thread_ids: [
            { thread_id: 11, boundary_level: 30, xp_cost: 10, dev_points_to_boundary: 5 },
          ],
        })
      ) as ReturnType<typeof magicQueries.useThreadHubSummary>
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('thread-state-badge-near_xp_lock')).toBeInTheDocument();
  });

  it('shows blocked badge for a thread in blocked_thread_ids', () => {
    vi.mocked(magicQueries.useThreads).mockReturnValue(
      makeQueryResult({
        count: 1,
        next: null,
        previous: null,
        results: [makeThread({ id: 12 })],
      }) as ReturnType<typeof magicQueries.useThreads>
    );
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(makeSummary({ blocked_thread_ids: [12] })) as ReturnType<
        typeof magicQueries.useThreadHubSummary
      >
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('thread-state-badge-blocked')).toBeInTheDocument();
  });

  it('navigates to /threads/:id when a thread card is clicked', () => {
    vi.mocked(magicQueries.useThreads).mockReturnValue(
      makeQueryResult({
        count: 1,
        next: null,
        previous: null,
        results: [makeThread({ id: 99 })],
      }) as ReturnType<typeof magicQueries.useThreads>
    );
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(makeSummary()) as ReturnType<typeof magicQueries.useThreadHubSummary>
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    fireEvent.click(screen.getByTestId('thread-card-99'));
    expect(mockNavigate).toHaveBeenCalledWith('/threads/99');
  });

  it('Weave New button click handler exists (does not throw)', () => {
    render(<ThreadHubPage />, { wrapper: createWrapper() });
    // Empty state renders two "Weave New" elements; click the header button (index 0)
    const weaveButtons = screen.getAllByRole('button', { name: 'Weave New' });
    expect(() => {
      fireEvent.click(weaveButtons[0]);
    }).not.toThrow();
  });

  it('shows loading skeleton for balances when summary is loading', () => {
    vi.mocked(magicQueries.useThreadHubSummary).mockReturnValue(
      makeQueryResult(undefined, true) as ReturnType<typeof magicQueries.useThreadHubSummary>
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    // Skeleton elements use the skeleton role or can be found by their class
    const skeletons = document.querySelectorAll('.animate-pulse, [class*="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows loading skeleton for threads when threads are loading', () => {
    vi.mocked(magicQueries.useThreads).mockReturnValue(
      makeQueryResult(undefined, true) as ReturnType<typeof magicQueries.useThreads>
    );

    render(<ThreadHubPage />, { wrapper: createWrapper() });
    const skeletons = document.querySelectorAll('.animate-pulse, [class*="skeleton"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
