/**
 * MyAGMClaimsPage Tests
 *
 * Tests rendering of status tabs, empty states per tab, loading skeleton,
 * claim rows, and 403 not-a-GM state.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { MyAGMClaimsPage } from '../pages/MyAGMClaimsPage';
import type { AssistantGMClaim, PaginatedResponse } from '../types';

// ---------------------------------------------------------------------------
// Mock API modules
// We mock listAssistantGMClaims and also getBeat (used by MyClaimRow → useBeat).
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  listAssistantGMClaims: vi.fn(),
  getBeat: vi.fn(),
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
// Fixtures
// ---------------------------------------------------------------------------

function makeClaim(status: string, overrides: Partial<AssistantGMClaim> = {}): AssistantGMClaim {
  return {
    id: Math.floor(Math.random() * 1000) + 1,
    beat: 50,
    assistant_gm: 7,
    status: status as AssistantGMClaim['status'],
    approved_by: null,
    rejection_note: '',
    framing_note: '',
    requested_at: '2026-04-01T10:00:00Z',
    updated_at: '2026-04-01T10:00:00Z',
    ...overrides,
  };
}

function makeClaimsResponse(claims: AssistantGMClaim[]): PaginatedResponse<AssistantGMClaim> {
  return { count: claims.length, next: null, previous: null, results: claims };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockClaimsForStatus(status: string, claims: AssistantGMClaim[]) {
  vi.mocked(api.listAssistantGMClaims).mockImplementation(
    (params?: { status?: string; page_size?: number }) => {
      if (params?.status === status) {
        return Promise.resolve(makeClaimsResponse(claims));
      }
      return Promise.resolve(makeClaimsResponse([]));
    }
  );
  // Ensure getBeat is always set up to avoid throwOnError blowup in useBeat
  vi.mocked(api.getBeat).mockResolvedValue(stubBeat as never);
}

const stubBeat = {
  id: 50,
  episode: 10,
  predicate_type: 'gm_marked' as const,
  outcome: 'unsatisfied' as const,
  visibility: 'visible' as const,
  internal_description: 'A mysterious encounter in the fog.',
  player_hint: undefined,
  player_resolution_text: undefined,
  order: 1,
  required_level: undefined,
  required_achievement: undefined,
  required_condition_template: undefined,
  required_codex_entry: undefined,
  referenced_story: undefined,
  referenced_milestone_type: undefined,
  referenced_chapter: undefined,
  referenced_episode: undefined,
  required_points: undefined,
  agm_eligible: true,
  deadline: undefined,
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-01T00:00:00Z',
};

function mockAllEmpty() {
  vi.mocked(api.listAssistantGMClaims).mockResolvedValue(makeClaimsResponse([]));
  vi.mocked(api.getBeat).mockResolvedValue(stubBeat as never);
}

function make403Error(): Error & { status: number } {
  const err = new Error('Forbidden') as Error & { status: number };
  err.status = 403;
  return err;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('MyAGMClaimsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: getBeat returns a stub beat so useBeat doesn't blow up
    vi.mocked(api.getBeat).mockResolvedValue(stubBeat as never);
  });

  it('renders page heading', async () => {
    mockAllEmpty();
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });
    expect(screen.getByText('My AGM Claims')).toBeInTheDocument();
  });

  it('renders all status tabs', async () => {
    mockAllEmpty();
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('tab-requested')).toBeInTheDocument();
    expect(screen.getByTestId('tab-approved')).toBeInTheDocument();
    expect(screen.getByTestId('tab-rejected')).toBeInTheDocument();
    expect(screen.getByTestId('tab-completed')).toBeInTheDocument();
    expect(screen.getByTestId('tab-cancelled')).toBeInTheDocument();
  });

  it('defaults to Requested tab and shows empty state', async () => {
    mockAllEmpty();
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
    expect(screen.getByText('No pending claim requests.')).toBeInTheDocument();
  });

  it('renders claim rows on Requested tab when data loaded', async () => {
    const requestedClaim = makeClaim('requested');
    mockClaimsForStatus('requested', [requestedClaim]);
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('my-claim-row')).toBeInTheDocument();
    });
    // The my-claim-row is present; verify the beat description appears
    expect(screen.getByText('A mysterious encounter in the fog.')).toBeInTheDocument();
  });

  it('shows cancel button on requested claim', async () => {
    const requestedClaim = makeClaim('requested');
    mockClaimsForStatus('requested', [requestedClaim]);
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel claim/i })).toBeInTheDocument();
    });
  });

  it('switches to Approved tab on click', async () => {
    const user = userEvent.setup();
    mockAllEmpty();
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('tab-approved'));

    await waitFor(() => {
      expect(screen.getByText('No approved claims right now.')).toBeInTheDocument();
    });
  });

  it('shows rejection note on Rejected tab', async () => {
    const user = userEvent.setup();
    const rejectedClaim = makeClaim('rejected', {
      rejection_note: 'Not enough scene experience yet.',
    });
    mockClaimsForStatus('rejected', [rejectedClaim]);
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });

    await user.click(screen.getByTestId('tab-rejected'));

    await waitFor(() => {
      expect(screen.getByTestId('my-claim-row')).toBeInTheDocument();
    });
    expect(screen.getByText('Not enough scene experience yet.')).toBeInTheDocument();
  });

  it('shows not-a-GM page on 403', async () => {
    vi.mocked(api.listAssistantGMClaims).mockRejectedValue(make403Error());
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });
  });

  it('renders loading skeleton during pending state', () => {
    vi.mocked(api.listAssistantGMClaims).mockReturnValue(new Promise(() => {}));
    render(<MyAGMClaimsPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('claims-skeleton')).toBeInTheDocument();
  });
});
