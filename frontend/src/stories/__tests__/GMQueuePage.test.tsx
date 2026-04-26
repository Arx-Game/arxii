/**
 * GMQueuePage Tests
 *
 * Tests rendering of the three sections, empty states, scope filter chips,
 * loading skeleton, and the 403 not-a-GM error state.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { GMQueuePage } from '../pages/GMQueuePage';
import type { GMQueueResponse } from '../types';

// ---------------------------------------------------------------------------
// Mock the API module directly (not the query hook, because the page uses
// useQuery directly to control throwOnError behavior).
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  getGMQueue: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Fixture data
// ---------------------------------------------------------------------------

const emptyResponse: GMQueueResponse = {
  episodes_ready_to_run: [],
  pending_agm_claims: [],
  assigned_session_requests: [],
};

const fullResponse: GMQueueResponse = {
  episodes_ready_to_run: [
    {
      story_id: 1,
      story_title: 'Who Am I?',
      scope: 'character',
      episode_id: 10,
      episode_title: 'The Reckoning',
      progress_type: 'character',
      progress_id: 5,
      eligible_transitions: [
        { transition_id: 1, mode: 'auto' as const },
        { transition_id: 2, mode: 'gm_choice' as const },
      ],
      open_session_request_id: 3,
    },
    {
      story_id: 2,
      story_title: 'Siege of Northhold',
      scope: 'group',
      episode_id: 20,
      episode_title: 'The Siege',
      progress_type: 'group',
      progress_id: 8,
      eligible_transitions: [{ transition_id: 3, mode: 'auto' as const }],
      open_session_request_id: null,
    },
  ],
  pending_agm_claims: [
    {
      claim_id: 101,
      beat_id: 50,
      beat_internal_description: 'Infiltrate the fortress under cover of night.',
      story_title: 'Siege of Northhold',
      assistant_gm_id: 7,
      requested_at: '2026-04-01T10:00:00Z',
    },
  ],
  assigned_session_requests: [
    {
      session_request_id: 201,
      episode_id: 10,
      episode_title: 'The Reckoning',
      story_title: 'Who Am I?',
      status: 'scheduled',
      event_id: 42,
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockSuccess(response: GMQueueResponse) {
  vi.mocked(api.getGMQueue).mockResolvedValue(response);
}

function mockLoading() {
  vi.mocked(api.getGMQueue).mockReturnValue(new Promise(() => {}));
}

function make403Error(): Error & { status: number } {
  const err = new Error('Failed to load GM queue') as Error & { status: number };
  err.status = 403;
  return err;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GMQueuePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders all three section headers', async () => {
    mockSuccess(emptyResponse);
    render(<GMQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('episodes-section')).toBeInTheDocument();
      expect(screen.getByTestId('claims-section')).toBeInTheDocument();
      expect(screen.getByTestId('session-requests-section')).toBeInTheDocument();
    });

    expect(screen.getByText('Episodes Ready to Run')).toBeInTheDocument();
    expect(screen.getByText('AGM Claims Pending Approval')).toBeInTheDocument();
    expect(screen.getByText('My Session Requests')).toBeInTheDocument();
  });

  it('renders episode cards, claim rows, and session request rows from full response', async () => {
    mockSuccess(fullResponse);
    render(<GMQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId('episode-ready-card')).toHaveLength(2);
    });

    // "Who Am I?" appears in both the episodes section and session requests section
    expect(screen.getAllByText('Who Am I?').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Siege of Northhold').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('pending-claim-row')).toBeInTheDocument();
    expect(screen.getByTestId('assigned-session-request-row')).toBeInTheDocument();
  });

  it('shows empty state for episodes section when no episodes', async () => {
    mockSuccess(emptyResponse);
    render(<GMQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('No episodes ready to run right now.')).toBeInTheDocument();
    });
  });

  it('shows empty state for claims section when no claims', async () => {
    mockSuccess(emptyResponse);
    render(<GMQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('No AGM claims awaiting your approval.')).toBeInTheDocument();
    });
  });

  it('shows empty state for session requests section when no requests', async () => {
    mockSuccess(emptyResponse);
    render(<GMQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('No session requests assigned to you.')).toBeInTheDocument();
    });
  });

  it('renders loading skeletons during pending state', () => {
    mockLoading();
    const { container } = render(<GMQueuePage />, { wrapper: createWrapper() });

    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('renders section skeleton placeholders', () => {
    mockLoading();
    render(<GMQueuePage />, { wrapper: createWrapper() });

    expect(screen.getAllByTestId('section-skeleton').length).toBeGreaterThan(0);
  });

  it('renders the not-a-GM message on 403 error', async () => {
    vi.mocked(api.getGMQueue).mockRejectedValue(make403Error());
    render(<GMQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });

    expect(screen.getByText(/You don't have a GM profile/i)).toBeInTheDocument();
  });

  it('scope filter chip filters episodes by scope', async () => {
    const user = userEvent.setup();
    mockSuccess(fullResponse);
    render(<GMQueuePage />, { wrapper: createWrapper() });

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getAllByTestId('episode-ready-card')).toHaveLength(2);
    });

    // Click "Group" filter chip — filters to only group-scope episodes
    await user.click(screen.getByRole('button', { name: 'Group' }));

    // Only the group-scope episode card should be visible
    expect(screen.getAllByTestId('episode-ready-card')).toHaveLength(1);
    // "Siege of Northhold" appears in the episode card (and also in the claim row)
    expect(screen.getAllByText('Siege of Northhold').length).toBeGreaterThanOrEqual(1);
    // "Who Am I?" episode card should not be visible (still shows in session request row)
    const episodesSection = screen.getByTestId('episodes-section');
    expect(episodesSection.querySelectorAll('[data-testid="episode-ready-card"]')).toHaveLength(1);
  });

  it('scope filter "All" shows all episodes', async () => {
    const user = userEvent.setup();
    mockSuccess(fullResponse);
    render(<GMQueuePage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId('episode-ready-card')).toHaveLength(2);
    });

    // Switch to Group then back to All
    await user.click(screen.getByRole('button', { name: 'Group' }));
    expect(screen.getAllByTestId('episode-ready-card')).toHaveLength(1);

    await user.click(screen.getByRole('button', { name: 'All' }));
    expect(screen.getAllByTestId('episode-ready-card')).toHaveLength(2);
  });
});
