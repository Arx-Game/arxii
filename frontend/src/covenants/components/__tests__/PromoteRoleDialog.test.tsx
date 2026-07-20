/**
 * PromoteRoleDialog Tests
 *
 * Covers the controlled sub-role promotion dialog:
 *   1. Open with sub-roles present → renders the sub-role names.
 *   2. Select a sub-role + click Promote → usePromoteMembership.mutate called
 *      with { membershipId, targetSubroleId }.
 *   3. Mutation error → the backend `detail` message is shown inline.
 *   4. Empty sub-roles → "No sub-roles available." and no actionable Promote.
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { PromoteRoleDialog } from '../PromoteRoleDialog';
import type { CharacterCovenantRole, CovenantRoleWithParent } from '@/covenants/api';

// ---------------------------------------------------------------------------
// Mock query module
// ---------------------------------------------------------------------------

vi.mock('@/covenants/queries', () => ({
  useSubroles: vi.fn(),
  usePromoteMembership: vi.fn(),
}));

import { useSubroles, usePromoteMembership } from '@/covenants/queries';

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const makeMembership = (): CharacterCovenantRole =>
  ({
    id: 99,
    character_sheet: 42,
    covenant: 1,
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
    rank: { id: 1, name: 'Vanguard', tier: 1 },
    viewer_capabilities: {
      can_invite: false,
      can_kick: false,
      can_manage_ranks: false,
      can_request_gm: false,
    },
    engaged: true,
    joined_at: '2026-01-01T00:00:00Z',
    left_at: null,
    is_active: true,
    can_engage: false,
    engage_blocked_reason: null,
  }) as CharacterCovenantRole;

const makeSubrole = (overrides: Partial<CovenantRoleWithParent> = {}): CovenantRoleWithParent => ({
  id: 21,
  name: 'Banner-Bearer',
  slug: 'banner-bearer',
  covenant_type: 'battle',
  covenant_type_display: 'Covenant of Battle',
  sword_weight: '0.000',
  shield_weight: '0.000',
  crown_weight: '0.000',
  speed_rank: 1,
  description: 'Carries the host into the breach.',
  parent_role: 7,
  technique_specialties: [],
  ...overrides,
});

function mockSubroles(data: CovenantRoleWithParent[] | undefined, isLoading = false) {
  vi.mocked(useSubroles).mockReturnValue({
    data: isLoading ? undefined : data,
    isLoading,
  } as never);
}

function mockPromote(overrides: Record<string, unknown> = {}) {
  const mutate = vi.fn();
  vi.mocked(usePromoteMembership).mockReturnValue({
    mutate,
    isPending: false,
    isError: false,
    error: null,
    ...overrides,
  } as never);
  return mutate;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PromoteRoleDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the sub-role names when open with sub-roles present', () => {
    mockSubroles([makeSubrole(), makeSubrole({ id: 22, name: 'Shield-Wall' })]);
    mockPromote();

    render(
      <PromoteRoleDialog
        covenantId={1}
        membership={makeMembership()}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Banner-Bearer')).toBeInTheDocument();
    expect(screen.getByText('Shield-Wall')).toBeInTheDocument();
  });

  it('calls mutate with the membership id and selected sub-role id on Promote', () => {
    mockSubroles([makeSubrole()]);
    const mutate = mockPromote();

    render(
      <PromoteRoleDialog
        covenantId={1}
        membership={makeMembership()}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByText('Banner-Bearer'));
    fireEvent.click(screen.getByRole('button', { name: /^Promote$/i }));

    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toEqual({ membershipId: 99, targetSubroleId: 21 });
  });

  it('shows the backend error detail when the mutation errors', () => {
    mockSubroles([makeSubrole()]);
    mockPromote({
      isError: true,
      error: new Error('Member must be engaged to promote.'),
    });

    render(
      <PromoteRoleDialog
        covenantId={1}
        membership={makeMembership()}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Member must be engaged to promote.')).toBeInTheDocument();
  });

  it('shows a no-sub-roles message and no actionable Promote when the list is empty', () => {
    mockSubroles([]);
    const mutate = mockPromote();

    render(
      <PromoteRoleDialog
        covenantId={1}
        membership={makeMembership()}
        open
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/No sub-roles available\./i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Promote$/i })).not.toBeInTheDocument();
    expect(mutate).not.toHaveBeenCalled();
  });
});
