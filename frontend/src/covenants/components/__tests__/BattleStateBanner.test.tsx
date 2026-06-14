/**
 * BattleStateBanner Tests
 *
 * Covers the battle-covenant dormant/risen banner:
 *   1. Battle + dormant + active member + sheet + rise ritual present →
 *      renders the dormant banner with an ENABLED "Raise" button; clicking it
 *      opens the RitualSessionDraftDialog (mocked).
 *   2. Battle + risen + active member → renders a "Stand Down" button; clicking
 *      it calls the stand-down mutation's mutate.
 *   3. Non-battle covenant → renders nothing.
 *   4. Battle + dormant but NOT an active member → "Raise" is not actionable
 *      (disabled).
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { BattleStateBanner } from '../BattleStateBanner';
import type { CovenantWithBattleState } from '@/covenants/api';
import type { RitualWithSchema, PaginatedRitualList } from '@/rituals/types';

// ---------------------------------------------------------------------------
// Mock query modules
// ---------------------------------------------------------------------------

vi.mock('@/covenants/queries', () => ({
  useStandDownCovenant: vi.fn(),
}));

vi.mock('@/rituals/queries', () => ({
  useRituals: vi.fn(),
}));

// Stub the dialog so we can assert open state without rendering its internals.
vi.mock('@/rituals/components/RitualSessionDraftDialog', () => ({
  RitualSessionDraftDialog: ({ open, ritual }: { open: boolean; ritual: RitualWithSchema }) =>
    open ? <div data-testid="draft-dialog">Drafting {ritual.name}</div> : null,
}));

import { useStandDownCovenant } from '@/covenants/queries';
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

const makeCovenant = (overrides: Partial<CovenantWithBattleState> = {}): CovenantWithBattleState =>
  ({
    id: 7,
    name: 'The Iron Banner',
    covenant_type: 'battle',
    covenant_type_display: 'Covenant of Battle',
    is_dormant: true,
    battle_binding: 'standing',
    battle_binding_display: 'Standing',
    ...overrides,
  }) as CovenantWithBattleState;

const makeRiseRitual = (overrides: Partial<RitualWithSchema> = {}): RitualWithSchema =>
  ({
    id: 200,
    name: 'Call the Banners',
    description: '',
    narrative_prose: '',
    hedge_accessible: false,
    glimpse_eligible: false,
    execution_kind: 'SERVICE',
    input_schema: null,
    author_account_id: null,
    check_config: null,
    client_hosted: false,
    participation_rule: 'FORMATION',
    min_participants: null,
    max_participants: null,
    ...overrides,
  }) as RitualWithSchema;

function mockRituals(rituals: RitualWithSchema[], isLoading = false) {
  const data: PaginatedRitualList = {
    count: rituals.length,
    next: null,
    previous: null,
    results: rituals,
  };
  vi.mocked(useRituals).mockReturnValue({
    data: isLoading ? undefined : data,
    isLoading,
  } as never);
}

function mockStandDown(mutate = vi.fn()) {
  vi.mocked(useStandDownCovenant).mockReturnValue({
    mutate,
    isPending: false,
  } as never);
  return mutate;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BattleStateBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockStandDown();
  });

  it('renders the dormant banner with an enabled Raise button that opens the dialog', async () => {
    const user = userEvent.setup();
    mockRituals([makeRiseRitual()]);

    render(
      <BattleStateBanner
        covenant={makeCovenant({ is_dormant: true })}
        characterSheetId={42}
        isActiveMember={true}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/this battle covenant is dormant/i)).toBeInTheDocument();
    const button = screen.getByRole('button', { name: /raise/i });
    expect(button).toBeEnabled();

    expect(screen.queryByTestId('draft-dialog')).not.toBeInTheDocument();
    await user.click(button);
    expect(screen.getByTestId('draft-dialog')).toBeInTheDocument();
  });

  it('renders a Stand Down button that calls the stand-down mutation when risen', async () => {
    const user = userEvent.setup();
    const mutate = mockStandDown();
    mockRituals([makeRiseRitual()]);

    render(
      <BattleStateBanner
        covenant={makeCovenant({ is_dormant: false })}
        characterSheetId={42}
        isActiveMember={true}
      />,
      { wrapper: createWrapper() }
    );

    const button = screen.getByRole('button', { name: /stand down/i });
    expect(button).toBeEnabled();
    await user.click(button);
    expect(mutate).toHaveBeenCalled();
  });

  it('renders nothing for a non-battle covenant', () => {
    mockRituals([makeRiseRitual()]);

    const { container } = render(
      <BattleStateBanner
        covenant={makeCovenant({ covenant_type: 'durance' })}
        characterSheetId={42}
        isActiveMember={true}
      />,
      { wrapper: createWrapper() }
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('disables Raise for a non-active member', () => {
    mockRituals([makeRiseRitual()]);

    render(
      <BattleStateBanner
        covenant={makeCovenant({ is_dormant: true })}
        characterSheetId={42}
        isActiveMember={false}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByRole('button', { name: /raise/i })).toBeDisabled();
  });
});
