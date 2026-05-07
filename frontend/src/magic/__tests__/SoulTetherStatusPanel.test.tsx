/**
 * SoulTetherStatusPanel Tests
 *
 * Tests for the SoulTetherStatusPanel component which displays the caller's
 * Soul Tether bonds using relationship IDs.
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import { describe, it, expect, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import type { SoulTetherDetail } from '../types';
import type { useSoulTetherDetail } from '../queries';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useSoulTetherDetail: vi.fn(),
}));

vi.mock('@/magic/components/HollowBar', () => ({
  HollowBar: ({ current, max }: { current: number; max: number }) => (
    <div data-testid="hollow-bar">
      {current}/{max}
    </div>
  ),
}));

import * as magicQueries from '@/magic/queries';
import { SoulTetherStatusPanel } from '../components/SoulTetherStatusPanel';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function makeTetherDetail(overrides: Partial<SoulTetherDetail> = {}): SoulTetherDetail {
  return {
    relationship_id: 1,
    is_soul_tether: true,
    soul_tether_role: 'ABYSSAL',
    sinner_sheet_id: 10,
    sineater_sheet_id: 20,
    hollow_current: 5,
    hollow_max: 20,
    sineater_lifetime_helped: 42,
    sinner_corruption_stage: 1,
    sineater_strain_stage: 0,
    ...overrides,
  };
}

function makeQueryResult(
  overrides: Partial<ReturnType<typeof useSoulTetherDetail>> = {}
): ReturnType<typeof useSoulTetherDetail> {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    isPending: false,
    isSuccess: false,
    status: 'pending',
    fetchStatus: 'idle',
    isFetching: false,
    isRefetching: false,
    isLoadingError: false,
    isRefetchError: false,
    isPlaceholderData: false,
    isStale: false,
    dataUpdatedAt: 0,
    errorUpdatedAt: 0,
    failureCount: 0,
    failureReason: null,
    errorUpdateCount: 0,
    isInitialLoading: false,
    isFetched: false,
    isFetchedAfterMount: false,
    isPaused: false,
    refetch: vi.fn(),
    promise: Promise.resolve(undefined) as unknown,
    ...overrides,
  } as unknown as ReturnType<typeof useSoulTetherDetail>;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SoulTetherStatusPanel', () => {
  beforeEach(() => {
    vi.mocked(magicQueries.useSoulTetherDetail).mockReturnValue(
      makeQueryResult({ isSuccess: true, status: 'success' })
    );
  });

  it('renders empty state when relationshipIds is empty', () => {
    render(<SoulTetherStatusPanel relationshipIds={[]} />, { wrapper: createWrapper() });

    expect(screen.getByText('No active soul tethers.')).toBeInTheDocument();
  });

  it('renders a card with "Soul Tethers" header', () => {
    render(<SoulTetherStatusPanel relationshipIds={[]} />, { wrapper: createWrapper() });

    expect(screen.getByText('Soul Tethers')).toBeInTheDocument();
  });

  it('renders one row per relationshipId', () => {
    const detail1 = makeTetherDetail({
      relationship_id: 1,
      sinner_sheet_id: 10,
      sineater_sheet_id: 20,
    });
    const detail2 = makeTetherDetail({
      relationship_id: 2,
      sinner_sheet_id: 30,
      sineater_sheet_id: 40,
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      const detail = id === 1 ? detail1 : detail2;
      return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
    });

    render(<SoulTetherStatusPanel relationshipIds={[1, 2]} />, { wrapper: createWrapper() });

    const hollowBars = screen.getAllByTestId('hollow-bar');
    expect(hollowBars).toHaveLength(2);
  });

  it('shows bonded character name from bondedCharacterNames prop', () => {
    const detail = makeTetherDetail({
      relationship_id: 5,
      sinner_sheet_id: 10,
      sineater_sheet_id: 20,
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      if (id === 5) {
        return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
      }
      return makeQueryResult({ isSuccess: true, status: 'success' });
    });

    render(
      <SoulTetherStatusPanel
        relationshipIds={[5]}
        callerSheetId={10}
        bondedCharacterNames={{ 5: 'Elowen Ashveil' }}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Elowen Ashveil')).toBeInTheDocument();
  });

  it('shows sheet ID fallback when no name is provided', () => {
    const detail = makeTetherDetail({
      relationship_id: 7,
      sinner_sheet_id: 10,
      sineater_sheet_id: 99,
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      if (id === 7) {
        return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
      }
      return makeQueryResult({ isSuccess: true, status: 'success' });
    });

    // callerSheetId=10 means sineater_sheet_id=99 is the bonded character
    render(<SoulTetherStatusPanel relationshipIds={[7]} callerSheetId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('#99')).toBeInTheDocument();
  });

  it('shows role label (Sinner) when caller is the sinner', () => {
    const detail = makeTetherDetail({
      relationship_id: 3,
      sinner_sheet_id: 10,
      sineater_sheet_id: 20,
      soul_tether_role: 'ABYSSAL',
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      if (id === 3) {
        return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
      }
      return makeQueryResult({ isSuccess: true, status: 'success' });
    });

    // callerSheetId=10 matches sinner_sheet_id=10 → caller is Sinner
    render(<SoulTetherStatusPanel relationshipIds={[3]} callerSheetId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('Sinner')).toBeInTheDocument();
  });

  it('shows role label (Sineater) when caller is the sineater', () => {
    const detail = makeTetherDetail({
      relationship_id: 4,
      sinner_sheet_id: 10,
      sineater_sheet_id: 20,
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      if (id === 4) {
        return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
      }
      return makeQueryResult({ isSuccess: true, status: 'success' });
    });

    // callerSheetId=20 matches sineater_sheet_id=20 → caller is Sineater
    render(<SoulTetherStatusPanel relationshipIds={[4]} callerSheetId={20} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('Sineater')).toBeInTheDocument();
  });

  it('shows HollowBar for each bond', () => {
    const detail = makeTetherDetail({
      relationship_id: 6,
      hollow_current: 8,
      hollow_max: 30,
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      if (id === 6) {
        return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
      }
      return makeQueryResult({ isSuccess: true, status: 'success' });
    });

    render(<SoulTetherStatusPanel relationshipIds={[6]} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('hollow-bar')).toHaveTextContent('8/30');
  });

  it('shows lifetime_helped when caller is the Sineater', () => {
    const detail = makeTetherDetail({
      relationship_id: 8,
      sinner_sheet_id: 10,
      sineater_sheet_id: 20,
      sineater_lifetime_helped: 77,
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      if (id === 8) {
        return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
      }
      return makeQueryResult({ isSuccess: true, status: 'success' });
    });

    // callerSheetId=20 → Sineater → should show lifetime_helped
    render(<SoulTetherStatusPanel relationshipIds={[8]} callerSheetId={20} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText(/77/)).toBeInTheDocument();
    expect(screen.getByText(/helped/i)).toBeInTheDocument();
  });

  it('does NOT show lifetime_helped when caller is the Sinner', () => {
    const detail = makeTetherDetail({
      relationship_id: 9,
      sinner_sheet_id: 10,
      sineater_sheet_id: 20,
      sineater_lifetime_helped: 99,
    });

    vi.mocked(magicQueries.useSoulTetherDetail).mockImplementation((id) => {
      if (id === 9) {
        return makeQueryResult({ data: detail, isSuccess: true, status: 'success' });
      }
      return makeQueryResult({ isSuccess: true, status: 'success' });
    });

    // callerSheetId=10 → Sinner → should NOT show lifetime_helped
    render(<SoulTetherStatusPanel relationshipIds={[9]} callerSheetId={10} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByText(/helped/i)).not.toBeInTheDocument();
  });

  it('renders loading state when a bond query is loading', () => {
    vi.mocked(magicQueries.useSoulTetherDetail).mockReturnValue(
      makeQueryResult({ isLoading: true, isPending: true, status: 'pending' })
    );

    render(<SoulTetherStatusPanel relationshipIds={[1]} />, { wrapper: createWrapper() });

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders error state when a bond query fails', () => {
    vi.mocked(magicQueries.useSoulTetherDetail).mockReturnValue(
      makeQueryResult({
        isError: true,
        status: 'error',
        error: new Error('Network error'),
      })
    );

    render(<SoulTetherStatusPanel relationshipIds={[1]} />, { wrapper: createWrapper() });

    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });
});
