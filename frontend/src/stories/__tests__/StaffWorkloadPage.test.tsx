/**
 * StaffWorkloadPage Tests
 *
 * Covers:
 *  - Renders all five sections (stat cards, scope counts, per-GM table,
 *    stale stories, frontier stories)
 *  - Empty states per table section
 *  - ExpireBeatsButton: confirm dialog then fires mutation
 *  - Sort by days_stale on the stale-stories table
 *  - Loading skeleton renders during pending state
 *  - 403 Access Denied fallback
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { StaffWorkloadPage } from '../pages/StaffWorkloadPage';
import type { StaffWorkloadResponse } from '../types';

// ---------------------------------------------------------------------------
// Mock API module (page queries via useQuery({ queryFn: getStaffWorkload }))
// ---------------------------------------------------------------------------

vi.mock('../api', () => ({
  getStaffWorkload: vi.fn(),
  expireOverdueBeats: vi.fn(),
}));

import * as api from '../api';

// Mock sonner toast
vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from 'sonner';

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

const emptyResponse: StaffWorkloadResponse = {
  per_gm_queue_depth: [],
  stale_stories: [],
  stories_at_frontier: [],
  pending_agm_claims_count: 0,
  open_session_requests_count: 0,
  counts_by_scope: {},
};

const fullResponse: StaffWorkloadResponse = {
  pending_agm_claims_count: 3,
  open_session_requests_count: 5,
  counts_by_scope: { character: 4, group: 2, global: 1 },
  per_gm_queue_depth: [
    { gm_profile_id: 1, gm_name: 'Alice GM', episodes_ready: 7, pending_claims: 2 },
    { gm_profile_id: 2, gm_name: 'Bob GM', episodes_ready: 2, pending_claims: 0 },
    { gm_profile_id: 3, gm_name: 'Carol GM', episodes_ready: 5, pending_claims: 1 },
  ],
  stale_stories: [
    {
      story_id: 10,
      story_title: 'The Forgotten War',
      last_advanced_at: '2026-03-01T00:00:00Z',
      days_stale: 49,
    },
    {
      story_id: 11,
      story_title: 'Shadow Bridge',
      last_advanced_at: '2026-04-05T00:00:00Z',
      days_stale: 14,
    },
    {
      story_id: 12,
      story_title: 'An Old Grudge',
      last_advanced_at: '2026-03-15T00:00:00Z',
      days_stale: 35,
    },
  ],
  stories_at_frontier: [
    { story_id: 20, story_title: 'The Reckoning', scope: 'character' },
    { story_id: 21, story_title: 'Rise of Northhold', scope: 'group' },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockSuccess(response: StaffWorkloadResponse) {
  vi.mocked(api.getStaffWorkload).mockResolvedValue(response);
}

function mockLoading() {
  vi.mocked(api.getStaffWorkload).mockReturnValue(new Promise(() => {}));
}

function make403Error(): Error & { status: number } {
  const err = new Error('Forbidden') as Error & { status: number };
  err.status = 403;
  return err;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StaffWorkloadPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // -------------------------------------------------------------------------
  // Section rendering
  // -------------------------------------------------------------------------

  it('renders all five sections with full data', async () => {
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stat-cards-section')).toBeInTheDocument();
    });

    expect(screen.getByTestId('scope-section')).toBeInTheDocument();
    expect(screen.getByTestId('per-gm-section')).toBeInTheDocument();
    expect(screen.getByTestId('stale-stories-section')).toBeInTheDocument();
    expect(screen.getByTestId('frontier-section')).toBeInTheDocument();
    expect(screen.getByTestId('manual-actions-section')).toBeInTheDocument();
  });

  it('renders top-line count cards with correct values', async () => {
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stat-cards-section')).toBeInTheDocument();
    });

    // pending AGM claims = 3, stale stories = 3 → two "3" spans in the section
    const section = screen.getByTestId('stat-cards-section');
    expect(within(section).getAllByText('3')).toHaveLength(2);
    expect(within(section).getByText('5')).toBeInTheDocument(); // open session requests
    expect(within(section).getByText('2')).toBeInTheDocument(); // at frontier
    // Labels
    expect(within(section).getByText('Pending AGM Claims')).toBeInTheDocument();
    expect(within(section).getByText('Open Session Requests')).toBeInTheDocument();
    expect(within(section).getByText(/Stale Stories/i)).toBeInTheDocument();
    expect(within(section).getByText('At Frontier')).toBeInTheDocument();
  });

  it('renders scope counts strip', async () => {
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('scope-counts')).toBeInTheDocument();
    });

    const strip = screen.getByTestId('scope-counts');
    expect(within(strip).getByText('Character:')).toBeInTheDocument();
    expect(within(strip).getByText('Group:')).toBeInTheDocument();
    expect(within(strip).getByText('Global:')).toBeInTheDocument();
    // values
    expect(within(strip).getByText('4')).toBeInTheDocument();
    expect(within(strip).getByText('2')).toBeInTheDocument();
    expect(within(strip).getByText('1')).toBeInTheDocument();
  });

  it('renders per-GM table rows', async () => {
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('per-gm-table')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('per-gm-row');
    expect(rows).toHaveLength(3);
    expect(screen.getByText('Alice GM')).toBeInTheDocument();
    expect(screen.getByText('Bob GM')).toBeInTheDocument();
    expect(screen.getByText('Carol GM')).toBeInTheDocument();
  });

  it('renders stale stories table rows', async () => {
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stale-stories-table')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('stale-story-row');
    expect(rows).toHaveLength(3);
    expect(screen.getByText('The Forgotten War')).toBeInTheDocument();
    expect(screen.getByText('Shadow Bridge')).toBeInTheDocument();
  });

  it('renders frontier stories table rows', async () => {
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('frontier-stories-table')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('frontier-story-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('The Reckoning')).toBeInTheDocument();
    expect(screen.getByText('Rise of Northhold')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Empty states
  // -------------------------------------------------------------------------

  it('renders per-GM empty state when no GM data', async () => {
    mockSuccess(emptyResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('per-gm-empty')).toBeInTheDocument();
    });
    expect(screen.getByText('No GM workload data right now.')).toBeInTheDocument();
  });

  it('renders stale stories empty state when no stale stories', async () => {
    mockSuccess(emptyResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stale-stories-empty')).toBeInTheDocument();
    });
    expect(
      screen.getByText('No stories are stale (last advanced within 14 days).')
    ).toBeInTheDocument();
  });

  it('renders frontier stories empty state when none at frontier', async () => {
    mockSuccess(emptyResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('frontier-stories-empty')).toBeInTheDocument();
    });
    expect(screen.getByText('No stories at the authoring frontier.')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Loading skeleton
  // -------------------------------------------------------------------------

  it('renders loading skeleton during pending state', () => {
    mockLoading();
    const { container } = render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    expect(screen.getByTestId('workload-loading')).toBeInTheDocument();
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0);
  });

  it('renders table skeleton placeholders during loading', () => {
    mockLoading();
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    expect(screen.getAllByTestId('table-skeleton').length).toBeGreaterThan(0);
  });

  // -------------------------------------------------------------------------
  // 403 Access Denied
  // -------------------------------------------------------------------------

  it('renders Access Denied page on 403 error', async () => {
    vi.mocked(api.getStaffWorkload).mockRejectedValue(make403Error());
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });
    expect(screen.getByText(/only accessible to staff/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Sort by days_stale on stale stories table
  // -------------------------------------------------------------------------

  it('stale stories are sorted by days_stale desc by default', async () => {
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stale-stories-table')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('stale-story-row');
    // Default: days_stale desc — 49, 35, 14
    expect(within(rows[0]).getByText('The Forgotten War')).toBeInTheDocument();
    expect(within(rows[1]).getByText('An Old Grudge')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Shadow Bridge')).toBeInTheDocument();
  });

  it('clicking Days Stale header sorts asc then desc', async () => {
    const user = userEvent.setup();
    mockSuccess(fullResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('stale-stories-table')).toBeInTheDocument();
    });

    // Click once: already desc → toggles to asc (14, 35, 49)
    await user.click(screen.getByRole('button', { name: /days stale/i }));

    const rowsAsc = screen.getAllByTestId('stale-story-row');
    expect(within(rowsAsc[0]).getByText('Shadow Bridge')).toBeInTheDocument();
    expect(within(rowsAsc[2]).getByText('The Forgotten War')).toBeInTheDocument();

    // Click again: back to desc
    await user.click(screen.getByRole('button', { name: /days stale/i }));

    const rowsDesc = screen.getAllByTestId('stale-story-row');
    expect(within(rowsDesc[0]).getByText('The Forgotten War')).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // ExpireBeatsButton: confirm dialog → mutation
  // -------------------------------------------------------------------------

  it('ExpireBeatsButton shows the trigger button', async () => {
    mockSuccess(emptyResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('expire-beats-trigger')).toBeInTheDocument();
    });
  });

  it('ExpireBeatsButton opens confirm dialog on click', async () => {
    const user = userEvent.setup();
    mockSuccess(emptyResponse);
    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('expire-beats-trigger')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('expire-beats-trigger'));

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/Sweep overdue beats/i)).toBeInTheDocument();
    expect(screen.getByText(/idempotent and safe/i)).toBeInTheDocument();
  });

  it('ExpireBeatsButton fires mutation and shows toast on confirm', async () => {
    const user = userEvent.setup();
    vi.mocked(api.expireOverdueBeats).mockResolvedValue({ expired_count: 7 });
    mockSuccess(emptyResponse);

    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('expire-beats-trigger')).toBeInTheDocument();
    });

    // Open dialog
    await user.click(screen.getByTestId('expire-beats-trigger'));
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();

    // Confirm
    await user.click(screen.getByTestId('expire-beats-confirm'));

    await waitFor(() => {
      expect(api.expireOverdueBeats).toHaveBeenCalledTimes(1);
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Expired 7 overdue beats');
    });
  });

  it('ExpireBeatsButton handles singular beat count in toast', async () => {
    const user = userEvent.setup();
    vi.mocked(api.expireOverdueBeats).mockResolvedValue({ expired_count: 1 });
    mockSuccess(emptyResponse);

    render(<StaffWorkloadPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByTestId('expire-beats-trigger')).toBeInTheDocument();
    });

    await user.click(screen.getByTestId('expire-beats-trigger'));
    await user.click(screen.getByTestId('expire-beats-confirm'));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Expired 1 overdue beat');
    });
  });
});
