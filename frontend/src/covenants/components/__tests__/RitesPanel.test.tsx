/**
 * RitesPanel Tests
 *
 * Covers the covenant "Group Abilities" (rites) panel:
 *   1. A fully-gated-open rite (level + members met, active member, sheet set)
 *      renders an ENABLED Perform button.
 *   2. A rite failing members_present_met disables Perform and surfaces the
 *      member-count requirement reason.
 *   3. Clicking an enabled Perform opens the RitualSessionDraftDialog (mocked).
 *   4. No rites → empty-state message.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { RitesPanel } from '../RitesPanel';
import type { CovenantRiteRow, CovenantPowers } from '@/covenants/api';
import type { RitualWithSchema, PaginatedRitualList } from '@/rituals/types';

// ---------------------------------------------------------------------------
// Mock query modules
// ---------------------------------------------------------------------------

vi.mock('@/covenants/queries', () => ({
  useCovenantPowers: vi.fn(),
}));

vi.mock('@/rituals/queries', () => ({
  useRituals: vi.fn(),
}));

// Stub the dialog so we can assert open state without rendering its internals.
vi.mock('@/rituals/components/RitualSessionDraftDialog', () => ({
  RitualSessionDraftDialog: ({ open, ritual }: { open: boolean; ritual: RitualWithSchema }) =>
    open ? <div data-testid="draft-dialog">Drafting {ritual.name}</div> : null,
}));

import { useCovenantPowers } from '@/covenants/queries';
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

const makeRite = (overrides: Partial<CovenantRiteRow> = {}): CovenantRiteRow => ({
  id: 1,
  ritual: 100,
  covenant_type: 'WAR',
  covenant_type_display: 'War',
  min_covenant_level: 2,
  min_members_present: 3,
  granted_condition: null,
  base_severity: 1,
  severity_per_extra_participant: 1,
  max_severity: 5,
  duration_rounds: 4,
  level_met: true,
  members_present_met: true,
  ...overrides,
});

const makeRitual = (overrides: Partial<RitualWithSchema> = {}): RitualWithSchema =>
  ({
    id: 100,
    name: 'Banner Call',
    description: '',
    narrative_prose: '',
    hedge_accessible: false,
    glimpse_eligible: false,
    execution_kind: 'SERVICE',
    input_schema: null,
    author_account_id: null,
    check_config: null,
    client_hosted: false,
    participation_rule: 'SESSION',
    min_participants: null,
    max_participants: null,
    ...overrides,
  }) as RitualWithSchema;

function mockPowers(rites: CovenantRiteRow[], isLoading = false) {
  const data: CovenantPowers = { rites, role_powers: [] };
  vi.mocked(useCovenantPowers).mockReturnValue({
    data: isLoading ? undefined : data,
    isLoading,
  } as never);
}

function mockRituals(rituals: RitualWithSchema[]) {
  const data: PaginatedRitualList = {
    count: rituals.length,
    next: null,
    previous: null,
    results: rituals,
  };
  vi.mocked(useRituals).mockReturnValue({ data, isLoading: false } as never);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RitesPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an enabled Perform button for a fully-open rite', () => {
    mockPowers([makeRite()]);
    mockRituals([makeRitual()]);

    render(<RitesPanel covenantId={1} isActiveMember={true} characterSheetId={42} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('Banner Call')).toBeInTheDocument();
    const button = screen.getByRole('button', { name: /perform/i });
    expect(button).toBeEnabled();
  });

  it('disables Perform and shows the member-count reason when members are not met', () => {
    mockPowers([makeRite({ members_present_met: false, min_members_present: 4 })]);
    mockRituals([makeRitual()]);

    render(<RitesPanel covenantId={1} isActiveMember={true} characterSheetId={42} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByRole('button', { name: /perform/i })).toBeDisabled();
    expect(screen.getByText(/Requires 4 members present/i)).toBeInTheDocument();
  });

  it('opens the draft dialog when an enabled Perform is clicked', async () => {
    const user = userEvent.setup();
    mockPowers([makeRite()]);
    mockRituals([makeRitual()]);

    render(<RitesPanel covenantId={1} isActiveMember={true} characterSheetId={42} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('draft-dialog')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /perform/i }));
    expect(screen.getByTestId('draft-dialog')).toBeInTheDocument();
  });

  it('renders an empty-state message when there are no rites', () => {
    mockPowers([]);
    mockRituals([makeRitual()]);

    render(<RitesPanel covenantId={1} isActiveMember={true} characterSheetId={42} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText(/No group abilities available/i)).toBeInTheDocument();
  });
});
