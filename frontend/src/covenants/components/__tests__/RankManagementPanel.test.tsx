/**
 * RankManagementPanel tests
 *
 * 1. Returns null (renders nothing) when viewer lacks can_manage_ranks.
 * 2. Renders the panel with rank names when viewer has can_manage_ranks.
 * 3. Capability badges shown for ranks that have the flag, hidden for ranks that don't.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { RankManagementPanel } from '@/covenants/components/RankManagementPanel';
import type { ViewerCapabilities, CovenantRank, PaginatedCovenantRankList } from '@/covenants/api';

// ---------------------------------------------------------------------------
// Mock query hooks
// ---------------------------------------------------------------------------

vi.mock('@/covenants/queries', () => ({
  useCovenantRanks: vi.fn(),
  useCreateRank: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useUpdateRank: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDeleteRank: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useReorderRanks: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

import { useCovenantRanks } from '@/covenants/queries';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const COVENANT_ID = 3;

const NO_CAPS: ViewerCapabilities = {
  can_invite: false,
  can_kick: false,
  can_manage_ranks: false,
  can_request_gm: false,
};
const MANAGE_CAPS: ViewerCapabilities = {
  can_invite: false,
  can_kick: false,
  can_manage_ranks: true,
  can_request_gm: false,
};

function makeRank(overrides: Partial<CovenantRank>): CovenantRank {
  return {
    id: 1,
    covenant: COVENANT_ID,
    name: 'Member',
    tier: 2,
    description: '',
    can_invite: false,
    can_kick: false,
    can_manage_ranks: false,
    ...overrides,
  };
}

function mockRanks(ranks: CovenantRank[]) {
  const data: PaginatedCovenantRankList = {
    count: ranks.length,
    next: null,
    previous: null,
    results: ranks,
  };
  vi.mocked(useCovenantRanks).mockReturnValue({ data } as never);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RankManagementPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRanks([]);
  });

  it('renders nothing when viewer lacks can_manage_ranks', () => {
    mockRanks([makeRank({ id: 1, name: 'Founder', tier: 1 })]);

    const { container } = render(
      <RankManagementPanel covenantId={COVENANT_ID} viewerCapabilities={NO_CAPS} />,
      { wrapper: createWrapper() }
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders the panel with rank names when viewer has can_manage_ranks', () => {
    mockRanks([
      makeRank({ id: 1, name: 'Founder', tier: 1 }),
      makeRank({ id: 2, name: 'Elder', tier: 2 }),
      makeRank({ id: 3, name: 'Member', tier: 3 }),
    ]);

    render(<RankManagementPanel covenantId={COVENANT_ID} viewerCapabilities={MANAGE_CAPS} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('rank-management-panel')).toBeInTheDocument();
    expect(screen.getByText(/Rank Ladder/i)).toBeInTheDocument();
    expect(screen.getByText(/Founder/)).toBeInTheDocument();
    expect(screen.getByText(/Elder/)).toBeInTheDocument();
    expect(screen.getByText(/Member/)).toBeInTheDocument();
  });

  it('shows capability badges only for ranks that have them', () => {
    mockRanks([
      makeRank({
        id: 1,
        name: 'Founder',
        tier: 1,
        can_invite: true,
        can_kick: true,
        can_manage_ranks: true,
      }),
      makeRank({
        id: 2,
        name: 'Recruit',
        tier: 2,
        can_invite: false,
        can_kick: false,
        can_manage_ranks: false,
      }),
    ]);

    render(<RankManagementPanel covenantId={COVENANT_ID} viewerCapabilities={MANAGE_CAPS} />, {
      wrapper: createWrapper(),
    });

    // Founder row: all three badges should appear
    const badges = screen.getAllByText(/can_invite|can_kick|can_manage_ranks/);
    // Three capability badges from Founder's row; Recruit has none
    expect(badges.length).toBeGreaterThanOrEqual(3);

    // The badges for Founder should all be present
    expect(screen.getByText('can_invite')).toBeInTheDocument();
    expect(screen.getByText('can_kick')).toBeInTheDocument();
    expect(screen.getByText('can_manage_ranks')).toBeInTheDocument();
  });
});
