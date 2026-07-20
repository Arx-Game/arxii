/**
 * CovenantDetailPage tests
 *
 * Covers:
 *   1. Existing behavior intact — covenant header + member roster render.
 *   2. Panels mounted: BattleStateBanner, RitesPanel, RolePowersPanel, RankManagementPanel.
 *   3. The viewer's OWN membership row shows Promote; other rows do not.
 *   4. Kick button gating: shown when viewer has can_kick AND target tier > viewer tier.
 *   5. Kick button NOT shown when target has equal-or-lower tier number (higher authority).
 *   6. Rank badge rendered in each member row.
 *
 * Renders CovenantDetailInner directly (avoids router param plumbing).
 * Heavy children are stubbed to assert mounting + props.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { CovenantDetailInner } from '../pages/CovenantDetailPage';
import type { CovenantWithBattleState, CharacterCovenantRole } from '@/covenants/api';
import type { PaginatedCharacterCovenantRoleList } from '@/covenants/api';

// ---------------------------------------------------------------------------
// Mock query modules
// ---------------------------------------------------------------------------

vi.mock('@/covenants/queries', () => ({
  useCovenantDetail: vi.fn(),
  useCovenantMembers: vi.fn(),
  useEngageMembership: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useDisengageMembership: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useLeaveMembership: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useKickMember: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useCovenantRanks: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
  })),
  useAssignMemberToRank: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
}));

vi.mock('@/rituals/queries', () => ({
  useRituals: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  })),
}));

// ---------------------------------------------------------------------------
// Stub heavy children
// ---------------------------------------------------------------------------

vi.mock('@/covenants/components/BattleStateBanner', () => ({
  BattleStateBanner: (props: { covenant: CovenantWithBattleState; isActiveMember: boolean }) => (
    <div data-testid="battle-state-banner" data-active={String(props.isActiveMember)}>
      banner:{props.covenant.id}
    </div>
  ),
}));

vi.mock('@/covenants/components/RitesPanel', () => ({
  RitesPanel: (props: { covenantId: number; isActiveMember: boolean }) => (
    <div data-testid="rites-panel" data-active={String(props.isActiveMember)}>
      rites:{props.covenantId}
    </div>
  ),
}));

vi.mock('@/covenants/components/RolePowersPanel', () => ({
  RolePowersPanel: (props: { covenantId: number }) => (
    <div data-testid="role-powers-panel">powers:{props.covenantId}</div>
  ),
}));

vi.mock('@/covenants/components/PromoteRoleDialog', () => ({
  PromoteRoleDialog: (props: { open: boolean; covenantId: number }) =>
    props.open ? <div data-testid="promote-dialog">promote:{props.covenantId}</div> : null,
}));

vi.mock('@/rituals/components/RitualSessionDraftDialog', () => ({
  RitualSessionDraftDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="induction-dialog" /> : null,
}));

vi.mock('@/covenants/components/RankManagementPanel', () => ({
  RankManagementPanel: (props: { covenantId: number }) => (
    <div data-testid="rank-management-panel">ranks:{props.covenantId}</div>
  ),
}));

vi.mock('@/covenants/components/GroupStoryRequestPanel', () => ({
  GroupStoryRequestPanel: (props: { covenantId: number }) => (
    <div data-testid="group-story-request-panel">gm-request:{props.covenantId}</div>
  ),
}));

// ---------------------------------------------------------------------------
// Mock Redux auth — provide a puppeted character for characterSheetId
// ---------------------------------------------------------------------------

const OWN_SHEET_ID = 42;

const authState = {
  auth: {
    account: {
      id: 1,
      username: 'testuser',
      available_characters: [
        {
          id: OWN_SHEET_ID,
          name: 'Test Character',
          currently_puppeted_in_session: true,
        },
      ],
      pending_applications: [],
    },
  },
};

vi.mock('react-redux', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-redux')>();
  return {
    ...actual,
    useSelector: vi.fn((selector: (state: unknown) => unknown) => selector(authState)),
  };
});

import { useCovenantDetail, useCovenantMembers, useCovenantRanks } from '@/covenants/queries';
import { useRituals } from '@/rituals/queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
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

const COVENANT_ID = 7;

const makeCovenant = (overrides: Partial<CovenantWithBattleState> = {}): CovenantWithBattleState =>
  ({
    id: COVENANT_ID,
    name: 'The Iron Banner',
    covenant_type: 'battle',
    covenant_type_display: 'Covenant of Battle',
    sworn_objective: 'Hold the line.',
    member_count: 2,
    level: 3,
    is_active: true,
    is_dormant: true,
    battle_binding: 'standing',
    battle_binding_display: 'Standing',
    ...overrides,
  }) as CovenantWithBattleState;

/**
 * Build a membership fixture. `viewer_capabilities` defaults to all-false
 * (non-leader viewer); override to test capability gating.
 */
const makeMembership = (overrides: Partial<CharacterCovenantRole> = {}): CharacterCovenantRole =>
  ({
    id: 100,
    character_sheet: OWN_SHEET_ID,
    covenant: COVENANT_ID,
    covenant_role: {
      id: 7,
      name: 'Vanguard',
      slug: 'vanguard',
      covenant_type: 'battle',
      covenant_type_display: 'Covenant of Battle',
      sword_weight: '1.000',
      shield_weight: '0.000',
      crown_weight: '0.000',
      speed_rank: 1,
      description: 'The tip of the spear.',
      parent_role: null,
    },
    rank: { id: 1, name: 'Founder', tier: 1 },
    viewer_capabilities: {
      can_invite: false,
      can_kick: false,
      can_manage_ranks: false,
      can_request_gm: false,
    },
    engaged: false,
    joined_at: '2026-01-01T00:00:00Z',
    left_at: null,
    is_active: true,
    can_engage: true,
    engage_blocked_reason: null,
    ...overrides,
  }) as CharacterCovenantRole;

function mockDetail(covenant: CovenantWithBattleState | undefined, isLoading = false) {
  vi.mocked(useCovenantDetail).mockReturnValue({
    data: covenant,
    isLoading,
  } as never);
}

function mockMembers(members: CharacterCovenantRole[], isLoading = false) {
  const data: PaginatedCharacterCovenantRoleList = {
    count: members.length,
    next: null,
    previous: null,
    results: members,
  };
  vi.mocked(useCovenantMembers).mockReturnValue({
    data: isLoading ? undefined : data,
    isLoading,
  } as never);
}

function mockRanks(ranks: Array<{ id: number; name: string; tier: number }>) {
  vi.mocked(useCovenantRanks).mockReturnValue({
    data: { count: ranks.length, next: null, previous: null, results: ranks },
  } as never);
}

const INDUCTION_RITUAL = {
  id: 99,
  name: 'Covenant Induction',
  participation_rule: 'INDUCTION',
  input_schema: null,
  narrative_prose: null,
};

function mockRitualsWithInduction() {
  vi.mocked(useRituals).mockReturnValue({
    data: { count: 1, next: null, previous: null, results: [INDUCTION_RITUAL] },
    isLoading: false,
  } as never);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('CovenantDetailPage (CovenantDetailInner)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the covenant header and member roster (existing behavior intact)', () => {
    mockDetail(makeCovenant());
    mockMembers([makeMembership()]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.getByText('The Iron Banner')).toBeInTheDocument();
    expect(screen.getByTestId('member-roster')).toBeInTheDocument();
    expect(screen.getByText('Character #42')).toBeInTheDocument();
  });

  it('mounts BattleStateBanner, RitesPanel, RolePowersPanel, and RankManagementPanel', () => {
    mockDetail(makeCovenant());
    mockMembers([makeMembership()]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('battle-state-banner')).toBeInTheDocument();
    expect(screen.getByTestId('rites-panel')).toHaveTextContent(`rites:${COVENANT_ID}`);
    expect(screen.getByTestId('role-powers-panel')).toHaveTextContent(`powers:${COVENANT_ID}`);
    expect(screen.getByTestId('rank-management-panel')).toHaveTextContent(`ranks:${COVENANT_ID}`);
    // The viewer is an active member, so membership-aware panels know it.
    expect(screen.getByTestId('battle-state-banner')).toHaveAttribute('data-active', 'true');
    expect(screen.getByTestId('rites-panel')).toHaveAttribute('data-active', 'true');
  });

  it("shows a Promote button on the viewer's own active membership row only", () => {
    mockDetail(makeCovenant());
    mockMembers([
      makeMembership({ id: 100, character_sheet: OWN_SHEET_ID }),
      makeMembership({ id: 101, character_sheet: 999 }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    const rows = screen.getAllByTestId('member-row');
    expect(rows).toHaveLength(2);

    // Own row (sheet 42) has a Promote button.
    const promoteButtons = screen.getAllByRole('button', { name: /^Promote$/i });
    expect(promoteButtons).toHaveLength(1);
  });

  it("renders a Leave button on the viewer's own active membership row", () => {
    mockDetail(makeCovenant());
    mockMembers([makeMembership({ id: 100, character_sheet: OWN_SHEET_ID })]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('leave-button')).toBeInTheDocument();
  });

  it('shows kick button when viewer has can_kick and target has strictly higher tier', () => {
    // Viewer is at tier 1; target is at tier 2 (lower authority → can be kicked).
    mockDetail(makeCovenant());
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        rank: { id: 1, name: 'Founder', tier: 1 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: true,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
      makeMembership({
        id: 101,
        character_sheet: 999,
        rank: { id: 2, name: 'Member', tier: 2 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: true,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    const kickButtons = screen.getAllByTestId('kick-button');
    expect(kickButtons).toHaveLength(1);
  });

  it('renders NO kick button when target has the same tier (equal authority)', () => {
    mockDetail(makeCovenant());
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        rank: { id: 1, name: 'Elder', tier: 2 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: true,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
      makeMembership({
        id: 101,
        character_sheet: 999,
        rank: { id: 2, name: 'Elder', tier: 2 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: true,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('kick-button')).not.toBeInTheDocument();
  });

  it('renders NO kick button when target has lower tier number (higher authority)', () => {
    // Viewer tier 3, target tier 1 — viewer cannot kick a superior.
    mockDetail(makeCovenant());
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        rank: { id: 3, name: 'Recruit', tier: 3 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: true,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
      makeMembership({
        id: 101,
        character_sheet: 999,
        rank: { id: 1, name: 'Founder', tier: 1 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: true,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('kick-button')).not.toBeInTheDocument();
  });

  it('renders no kick button on any row when viewer lacks can_kick', () => {
    mockDetail(makeCovenant());
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        rank: { id: 1, name: 'Founder', tier: 1 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: false,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
      makeMembership({
        id: 101,
        character_sheet: 999,
        rank: { id: 2, name: 'Member', tier: 2 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: false,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('kick-button')).not.toBeInTheDocument();
  });

  it('renders a rank badge in each member row', () => {
    mockDetail(makeCovenant());
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        rank: { id: 1, name: 'Founder', tier: 1 },
      }),
      makeMembership({
        id: 101,
        character_sheet: 999,
        rank: { id: 2, name: 'Recruit', tier: 3 },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.getByText('Founder')).toBeInTheDocument();
    expect(screen.getByText('Recruit')).toBeInTheDocument();
  });

  it('shows a rank-assignment dropdown per active member when viewer can_manage_ranks', () => {
    mockDetail(makeCovenant());
    mockRanks([
      { id: 1, name: 'Founder', tier: 1 },
      { id: 2, name: 'Member', tier: 2 },
    ]);
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        rank: { id: 1, name: 'Founder', tier: 1 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: false,
          can_manage_ranks: true,
          can_request_gm: false,
        },
      }),
      makeMembership({
        id: 101,
        character_sheet: 999,
        rank: { id: 2, name: 'Member', tier: 2 },
        viewer_capabilities: {
          can_invite: false,
          can_kick: false,
          can_manage_ranks: true,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.getAllByTestId('assign-rank-select')).toHaveLength(2);
  });

  it('hides the rank-assignment dropdown when viewer lacks can_manage_ranks', () => {
    mockDetail(makeCovenant());
    mockRanks([
      { id: 1, name: 'Founder', tier: 1 },
      { id: 2, name: 'Member', tier: 2 },
    ]);
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        viewer_capabilities: {
          can_invite: false,
          can_kick: false,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('assign-rank-select')).not.toBeInTheDocument();
  });

  it('hides the Induct CTA when can_invite is false (even as active member)', () => {
    mockDetail(makeCovenant());
    mockRitualsWithInduction();
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        viewer_capabilities: {
          can_invite: false,
          can_kick: false,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('induct-member-button')).not.toBeInTheDocument();
  });

  it('shows the Induct CTA when can_invite is true and an induction ritual is present', () => {
    mockDetail(makeCovenant());
    mockRitualsWithInduction();
    mockMembers([
      makeMembership({
        id: 100,
        character_sheet: OWN_SHEET_ID,
        viewer_capabilities: {
          can_invite: true,
          can_kick: false,
          can_manage_ranks: false,
          can_request_gm: false,
        },
      }),
    ]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('induct-member-button')).toBeInTheDocument();
  });
});
