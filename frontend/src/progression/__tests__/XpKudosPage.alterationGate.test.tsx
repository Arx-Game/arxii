/**
 * XP/Kudos page — alteration gate alert tests (#877).
 *
 * The gate is per-character: spend_xp_on_unlock checks the SPENDING character's sheet
 * for an OPEN PendingAlteration before allowing any XP spend. These tests verify the
 * alert names the affected character(s) so multi-character players aren't misled.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { MemoryRouter } from 'react-router-dom';
import { authSlice } from '@/store/authSlice';
import { XpKudosPage } from '../XpKudosPage';
import type { PaginatedPendingAlterationList } from '@/magic/types';
import type { AccountProgressionData } from '../types';

// ---------------------------------------------------------------------------
// Sync vi.mock — factory hoisted before imports.
// ---------------------------------------------------------------------------

// Mock magic api so usePendingAlterations resolves without network calls.
vi.mock('@/magic/api', () => ({
  getPendingAlterations: vi.fn(),
  getAlterationLibrary: vi.fn(),
  resolveAlteration: vi.fn(),
  AlterationResolveError: class AlterationResolveError extends Error {
    fieldErrors: Record<string, string[]>;
    constructor(message: string, fieldErrors: Record<string, string[]> = {}) {
      super(message);
      this.name = 'AlterationResolveError';
      this.fieldErrors = fieldErrors;
    }
  },
}));

// Mock progression queries so the page renders without a real account-progression endpoint.
vi.mock('../queries', () => ({
  useAccountProgressionQuery: vi.fn(),
  useClaimKudosMutation: vi.fn(),
}));

import * as magicApi from '@/magic/api';
import * as progressionQueries from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const EMPTY_ALTERATIONS: PaginatedPendingAlterationList = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

const ONE_PENDING: PaginatedPendingAlterationList = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 7,
      character_id: 3,
      character_name: 'Velenosa',
      status: 'open' as const,
      tier: 3,
      tier_display: 'Touched',
      tier_caps: {
        social_cap: 3,
        weakness_cap: 3,
        resonance_cap: 3,
        visibility_required: false,
      } as unknown as Record<string, unknown>,
      origin_affinity_name: 'Abyssal',
      origin_resonance_name: 'Shadow',
      triggering_scene: null,
      created_at: '2026-06-01T00:00:00Z',
    },
  ],
};

const MINIMAL_PROGRESSION: AccountProgressionData = {
  xp: { total_earned: 100, total_spent: 20, current_available: 80 },
  kudos: { total_earned: 50, total_claimed: 10, current_available: 40 },
  xp_transactions: [],
  kudos_transactions: [],
  claim_categories: [],
};

// ---------------------------------------------------------------------------
// Wrapper helpers
// ---------------------------------------------------------------------------

function createAuthStore() {
  const store = configureStore({
    reducer: { auth: authSlice.reducer },
  });
  store.dispatch(
    authSlice.actions.setAccount({
      id: 1,
      username: 'testuser',
      email: 'test@example.com',
    } as Parameters<typeof authSlice.actions.setAccount>[0])
  );
  return store;
}

function renderWithProviders(ui: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const store = createAuthStore();
  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{ui}</MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('XpKudosPage — alteration gate alert', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: progression data loaded (no loading/error state).
    vi.mocked(progressionQueries.useAccountProgressionQuery).mockReturnValue({
      data: MINIMAL_PROGRESSION,
      isLoading: false,
      error: null,
    } as ReturnType<typeof progressionQueries.useAccountProgressionQuery>);
    // Default: useClaimKudosMutation returns a minimal stub.
    vi.mocked(progressionQueries.useClaimKudosMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
      reset: vi.fn(),
    } as unknown as ReturnType<typeof progressionQueries.useClaimKudosMutation>);
  });

  it('shows the gate alert naming the character when a pending alteration exists', async () => {
    vi.mocked(magicApi.getPendingAlterations).mockResolvedValue(ONE_PENDING);

    renderWithProviders(<XpKudosPage />);

    const alert = await screen.findByTestId('alteration-gate-alert');
    expect(alert).toBeInTheDocument();
    expect(alert).toHaveTextContent(/Velenosa carries an unresolved Mage Scar/);

    const link = screen.getByRole('link', { name: /resolve it/i });
    expect(link).toHaveAttribute('href', '/magic/alterations');
  });

  it('shows no gate alert when there are no pending alterations', async () => {
    vi.mocked(magicApi.getPendingAlterations).mockResolvedValue(EMPTY_ALTERATIONS);

    renderWithProviders(<XpKudosPage />);

    // Wait for the query to settle before asserting absence.
    await waitFor(() => expect(magicApi.getPendingAlterations).toHaveBeenCalled());

    expect(screen.queryByTestId('alteration-gate-alert')).not.toBeInTheDocument();
  });
});
