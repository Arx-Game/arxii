/**
 * XP/Kudos page — PathIntentCard mount tests (#543).
 *
 * Verifies that PathIntentCard appears when the character has a declared
 * path intent, and is absent (returns null / empty state) when intent is null.
 * Mirrors the AlterationGateAlert test pattern: vi.fn() mocks for both the
 * magic api module and progression queries, no network.
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
import type { PathIntentResponse } from '@/magic/types';
import type { AccountProgressionData } from '../types';

// ---------------------------------------------------------------------------
// Sync vi.mock — factories hoisted before imports.
// ---------------------------------------------------------------------------

// Mock the magic api so all hooks in @/magic/queries resolve without network.
vi.mock('@/magic/api', () => ({
  getPendingAlterations: vi.fn(),
  getAlterationLibrary: vi.fn(),
  resolveAlteration: vi.fn(),
  getPathIntent: vi.fn(),
  putPathIntent: vi.fn(),
  deletePathIntent: vi.fn(),
  AlterationResolveError: class AlterationResolveError extends Error {
    fieldErrors: Record<string, string[]>;
    constructor(message: string, fieldErrors: Record<string, string[]> = {}) {
      super(message);
      this.name = 'AlterationResolveError';
      this.fieldErrors = fieldErrors;
    }
  },
}));

// Mock progression queries so the page renders without the account-progression endpoint.
vi.mock('../queries', () => ({
  useAccountProgressionQuery: vi.fn(),
  useClaimKudosMutation: vi.fn(),
}));

import * as magicApi from '@/magic/api';
import * as progressionQueries from '../queries';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MINIMAL_PROGRESSION: AccountProgressionData = {
  xp: { total_earned: 100, total_spent: 20, current_available: 80 },
  kudos: { total_earned: 50, total_claimed: 10, current_available: 40 },
  xp_transactions: [],
  kudos_transactions: [],
  claim_categories: [],
};

const INTENT_PRESENT: PathIntentResponse = {
  intent: {
    id: 1,
    declared_at: '2026-06-01T00:00:00Z',
    intended_path: {
      id: 3,
      name: 'Path of Embers',
      stage: 2,
      stage_display: 'Kindled',
      description: 'A smoldering path.',
    },
  },
};

const INTENT_NULL: PathIntentResponse = { intent: null };

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

describe('XpKudosPage — PathIntentCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Stable progression data stub.
    vi.mocked(progressionQueries.useAccountProgressionQuery).mockReturnValue({
      data: MINIMAL_PROGRESSION,
      isLoading: false,
      error: null,
    } as ReturnType<typeof progressionQueries.useAccountProgressionQuery>);

    vi.mocked(progressionQueries.useClaimKudosMutation).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      error: null,
      reset: vi.fn(),
    } as unknown as ReturnType<typeof progressionQueries.useClaimKudosMutation>);

    // Default: no pending alterations (avoids gate alert noise).
    vi.mocked(magicApi.getPendingAlterations).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
  });

  it('renders PathIntentCard with path name when intent is declared', async () => {
    vi.mocked(magicApi.getPathIntent).mockResolvedValue(INTENT_PRESENT);

    renderWithProviders(<XpKudosPage />);

    const card = await screen.findByTestId('path-intent-card');
    expect(card).toBeInTheDocument();
    expect(card).toHaveTextContent('Path of Embers');
    expect(card).toHaveTextContent('Kindled');
  });

  it('does not render PathIntentCard when intent is null', async () => {
    vi.mocked(magicApi.getPathIntent).mockResolvedValue(INTENT_NULL);

    renderWithProviders(<XpKudosPage />);

    // Wait for the query to settle before asserting absence.
    await waitFor(() => expect(magicApi.getPathIntent).toHaveBeenCalled());

    expect(screen.queryByTestId('path-intent-card')).not.toBeInTheDocument();
  });
});
