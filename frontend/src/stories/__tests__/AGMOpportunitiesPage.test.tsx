/**
 * AGMOpportunitiesPage Tests
 *
 * Tests rendering of the opportunities list, filter chips, empty states,
 * loading skeleton, "already claimed" indicator, and 403 not-a-GM state.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { AGMOpportunitiesPage } from '../pages/AGMOpportunitiesPage';
import type { AssistantGMClaim, Beat, PaginatedResponse } from '../types';

// ---------------------------------------------------------------------------
// Mock API modules
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  listBeats: vi.fn(),
  listAssistantGMClaims: vi.fn(),
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

function makeBeat(overrides: Partial<Beat> = {}): Beat {
  return {
    id: 1,
    episode: 10,
    episode_title: 'The Reckoning',
    chapter_title: 'Chapter One',
    story_id: 5,
    story_title: 'Who Am I?',
    predicate_type: 'gm_marked',
    outcome: 'unsatisfied',
    visibility: 'visible',
    internal_description: 'Infiltrate the fortress under cover of night.',
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
    ...overrides,
  };
}

function makeClaim(beatId: number, status: string): AssistantGMClaim {
  return {
    id: 100,
    beat: beatId,
    assistant_gm: 7,
    status: status as AssistantGMClaim['status'],
    approved_by: null,
    rejection_note: '',
    framing_note: '',
    requested_at: '2026-04-01T10:00:00Z',
    updated_at: '2026-04-01T10:00:00Z',
  };
}

function makeBeatsResponse(beats: Beat[]): PaginatedResponse<Beat> {
  return { count: beats.length, next: null, previous: null, results: beats };
}

function makeClaimsResponse(claims: AssistantGMClaim[]): PaginatedResponse<AssistantGMClaim> {
  return { count: claims.length, next: null, previous: null, results: claims };
}

const emptyBeats = makeBeatsResponse([]);
const emptyClaimsResponse = makeClaimsResponse([]);

const singleBeat = makeBeat({ id: 1 });
const beatWithClaim = makeBeat({ id: 2, story_title: 'Siege of Northhold' });

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockSuccess(beats: PaginatedResponse<Beat>, claims: PaginatedResponse<AssistantGMClaim>) {
  vi.mocked(api.listBeats).mockResolvedValue(beats);
  vi.mocked(api.listAssistantGMClaims).mockResolvedValue(claims);
}

function mockLoading() {
  vi.mocked(api.listBeats).mockReturnValue(new Promise(() => {}));
  vi.mocked(api.listAssistantGMClaims).mockReturnValue(new Promise(() => {}));
}

function make403Error(): Error & { status: number } {
  const err = new Error('Forbidden') as Error & { status: number };
  err.status = 403;
  return err;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AGMOpportunitiesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders page heading', async () => {
    mockSuccess(emptyBeats, emptyClaimsResponse);
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });
    expect(screen.getByText('AGM Opportunities')).toBeInTheDocument();
  });

  it('renders loading skeleton while fetching', () => {
    mockLoading();
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });
    expect(screen.getByTestId('opportunities-skeleton')).toBeInTheDocument();
  });

  it('renders empty state when no beats', async () => {
    mockSuccess(emptyBeats, emptyClaimsResponse);
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    });
    expect(screen.getByText(/no unclaimed beats available/i)).toBeInTheDocument();
  });

  it('renders beat cards when data loaded', async () => {
    mockSuccess(makeBeatsResponse([singleBeat]), emptyClaimsResponse);
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByTestId('agm-opportunity-card')).toBeInTheDocument();
    });
    expect(screen.getByText('Who Am I?')).toBeInTheDocument();
    expect(screen.getByText(/infiltrate the fortress/i)).toBeInTheDocument();
  });

  it('shows "Already claimed" badge when user has an active claim (in All Open mode)', async () => {
    const user = userEvent.setup();
    const activeClaim = makeClaim(beatWithClaim.id, 'requested');
    mockSuccess(makeBeatsResponse([beatWithClaim]), makeClaimsResponse([activeClaim]));
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });

    // Wait for loading to complete (no cards yet since the beat is claimed)
    await waitFor(() => {
      expect(screen.queryByTestId('opportunities-skeleton')).not.toBeInTheDocument();
    });

    // Switch to "All Open" mode to see claimed beats
    await user.click(screen.getByRole('button', { name: 'All Open' }));

    await waitFor(() => {
      expect(screen.getByTestId('agm-opportunity-card')).toBeInTheDocument();
    });
    expect(screen.getByText('Already claimed')).toBeInTheDocument();
    // "Request Claim" button should not be present for already-claimed beat
    expect(screen.queryByRole('button', { name: /request claim/i })).not.toBeInTheDocument();
  });

  it('filters out claimed beats in "Available" mode', async () => {
    const activeClaim = makeClaim(beatWithClaim.id, 'approved');
    mockSuccess(makeBeatsResponse([singleBeat, beatWithClaim]), makeClaimsResponse([activeClaim]));
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByTestId('agm-opportunity-card')).toHaveLength(1);
    });
    // Only the unclaimed beat is shown
    expect(screen.getByText('Who Am I?')).toBeInTheDocument();
    expect(screen.queryByText('Siege of Northhold')).not.toBeInTheDocument();
  });

  it('shows all beats in "All Open" mode regardless of claims', async () => {
    const user = userEvent.setup();
    const activeClaim = makeClaim(beatWithClaim.id, 'approved');
    mockSuccess(makeBeatsResponse([singleBeat, beatWithClaim]), makeClaimsResponse([activeClaim]));
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByTestId('agm-opportunity-card')).toHaveLength(1);
    });

    await user.click(screen.getByRole('button', { name: 'All Open' }));

    expect(screen.getAllByTestId('agm-opportunity-card')).toHaveLength(2);
  });

  it('shows not-a-GM message on 403', async () => {
    vi.mocked(api.listBeats).mockRejectedValue(make403Error());
    vi.mocked(api.listAssistantGMClaims).mockResolvedValue(emptyClaimsResponse);
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });
  });

  it('filter chips are rendered', async () => {
    mockSuccess(emptyBeats, emptyClaimsResponse);
    render(<AGMOpportunitiesPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Available' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'All Open' })).toBeInTheDocument();
    });
  });
});
