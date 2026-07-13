/**
 * CrossoverInboxPage tests (#2075).
 *
 * Tests: rendering with invites, empty state, incoming/sent partitioning.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { Provider } from 'react-redux';
import { store } from '@/store/store';
import { CrossoverInboxPage } from '../pages/CrossoverInboxPage';
import type { CrossoverInvite } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockInvites: CrossoverInvite[] = [
  {
    id: 1,
    event: 10,
    from_gm: 5,
    from_gm_account: 99,
    to_story: 20,
    proposed_episode: null,
    accepted_episode: null,
    message: 'Please join our event!',
    response_note: '',
    status: 'pending',
    created_at: '2026-07-13T00:00:00Z',
    responded_at: null,
    updated_at: '2026-07-13T00:00:00Z',
  },
  {
    id: 2,
    event: 11,
    from_gm: 3,
    from_gm_account: 42,
    to_story: 21,
    proposed_episode: 30,
    accepted_episode: 30,
    message: '',
    response_note: 'Sounds great!',
    status: 'accepted',
    created_at: '2026-07-12T00:00:00Z',
    responded_at: '2026-07-12T12:00:00Z',
    updated_at: '2026-07-12T12:00:00Z',
  },
];

vi.mock('../queries', () => ({
  useCrossoverInvites: vi.fn(),
  useDeclineCrossoverInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useWithdrawCrossoverInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useAcceptCrossoverInvite: () => ({ mutate: vi.fn(), isPending: false }),
  useEpisodeScenesForScene: () => ({ data: undefined, isLoading: false }),
  crossoverKeys: {
    all: ['crossover'],
    invites: () => ['crossover', 'invites'],
    episodeScenes: () => ['crossover', 'episode-scenes'],
  },
}));

import { useCrossoverInvites } from '../queries';

const mockUseCrossoverInvites = vi.mocked(useCrossoverInvites);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CrossoverInboxPage />
        </MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CrossoverInboxPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the page title', () => {
    mockUseCrossoverInvites.mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    renderPage();
    expect(screen.getByText('Crossover Inbox')).toBeTruthy();
  });

  it('shows empty states when no invites', () => {
    mockUseCrossoverInvites.mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    renderPage();
    expect(screen.getByText(/No incoming crossover invites/i)).toBeTruthy();
    expect(screen.getByText(/No sent crossover invites/i)).toBeTruthy();
  });

  it('renders invite cards when data is present', () => {
    mockUseCrossoverInvites.mockReturnValue({
      data: { count: 2, next: null, previous: null, results: mockInvites },
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    renderPage();
    expect(screen.getByTestId('crossover-invite-card-1')).toBeTruthy();
    expect(screen.getByTestId('crossover-invite-card-2')).toBeTruthy();
  });

  it('shows accept/decline buttons for pending received invites', () => {
    mockUseCrossoverInvites.mockReturnValue({
      data: { count: 1, next: null, previous: null, results: [mockInvites[0]] },
      isLoading: false,
      isError: false,
      error: null,
    } as never);
    renderPage();
    expect(screen.getByTestId('invite-accept-1')).toBeTruthy();
    expect(screen.getByTestId('invite-decline-1')).toBeTruthy();
  });
});
