/**
 * CovenantDetailPage tests (C9)
 *
 * Covers the page-level wiring done in C9:
 *   1. Existing behavior intact — covenant header (name) + member roster render.
 *   2. The new panels are mounted: BattleStateBanner, RitesPanel, RolePowersPanel
 *      (asserted via lightweight stubs).
 *   3. The viewer's OWN active membership row shows a "Promote" button; a
 *      non-own row does not.
 *
 * Renders the exported `CovenantDetailInner` directly to avoid router param
 * plumbing. Heavy children are stubbed so we assert mounting + props rather
 * than their internals.
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
}));

vi.mock('@/rituals/queries', () => ({
  useRituals: vi.fn(() => ({
    data: { count: 0, next: null, previous: null, results: [] },
    isLoading: false,
  })),
}));

// ---------------------------------------------------------------------------
// Stub heavy children — assert mounting + key props
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

import { useCovenantDetail, useCovenantMembers } from '@/covenants/queries';

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
      archetype: 'sword',
      archetype_display: 'Sword',
      speed_rank: 1,
      description: 'The tip of the spear.',
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

  it('mounts BattleStateBanner, RitesPanel, and RolePowersPanel', () => {
    mockDetail(makeCovenant());
    mockMembers([makeMembership()]);

    render(<CovenantDetailInner covenantId={COVENANT_ID} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('battle-state-banner')).toBeInTheDocument();
    expect(screen.getByTestId('rites-panel')).toHaveTextContent(`rites:${COVENANT_ID}`);
    expect(screen.getByTestId('role-powers-panel')).toHaveTextContent(`powers:${COVENANT_ID}`);
    // The viewer is an active member, so the membership-aware panels know it.
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
});
