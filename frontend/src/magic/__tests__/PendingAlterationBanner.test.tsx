/**
 * PendingAlterationBanner tests (#877): hidden when clean, loud when marked.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { MemoryRouter } from 'react-router-dom';
import { authSlice } from '@/store/authSlice';
import { PendingAlterationBanner } from '../components/alterations/PendingAlterationBanner';
import type { PaginatedPendingAlterationList } from '../types';

// Sync vi.mock of '../api' — factory hoisted before imports.
vi.mock('../api', () => ({
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

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makePending(
  overrides: Partial<PaginatedPendingAlterationList['results'][number]> = {}
): PaginatedPendingAlterationList['results'][number] {
  return {
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
    ...overrides,
  };
}

const EMPTY_RESPONSE: PaginatedPendingAlterationList = {
  count: 0,
  next: null,
  previous: null,
  results: [],
};

const ONE_PENDING: PaginatedPendingAlterationList = {
  count: 1,
  next: null,
  previous: null,
  results: [makePending()],
};

const TWO_PENDING: PaginatedPendingAlterationList = {
  count: 2,
  next: null,
  previous: null,
  results: [makePending({ id: 7 }), makePending({ id: 8, character_name: 'Calista' })],
};

// ---------------------------------------------------------------------------
// Wrapper helpers
// ---------------------------------------------------------------------------

function createAuthStore(authenticated: boolean) {
  const store = configureStore({
    reducer: {
      auth: authSlice.reducer,
    },
  });

  if (authenticated) {
    store.dispatch(
      authSlice.actions.setAccount({
        id: 1,
        username: 'testuser',
        email: 'test@example.com',
      } as Parameters<typeof authSlice.actions.setAccount>[0])
    );
  }

  return store;
}

function renderWithProviders(ui: ReactNode, authenticated = true) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const store = createAuthStore(authenticated);

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

describe('PendingAlterationBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when there are no pending alterations', async () => {
    vi.mocked(api.getPendingAlterations).mockResolvedValue(EMPTY_RESPONSE);

    renderWithProviders(<PendingAlterationBanner />);

    // Wait for the query to settle before asserting absence
    await waitFor(() => expect(api.getPendingAlterations).toHaveBeenCalled());

    expect(screen.queryByTestId('pending-alteration-banner')).not.toBeInTheDocument();
  });

  it('renders banner with link when one pending alteration exists', async () => {
    vi.mocked(api.getPendingAlterations).mockResolvedValue(ONE_PENDING);

    renderWithProviders(<PendingAlterationBanner />);

    const banner = await screen.findByTestId('pending-alteration-banner');
    expect(banner).toBeInTheDocument();

    // Character name appears in message
    expect(banner).toHaveTextContent('Velenosa');

    // Resolve link points to /magic/alterations
    const link = screen.getByRole('link', { name: /resolve/i });
    expect(link).toHaveAttribute('href', '/magic/alterations');
  });

  it('renders count form when 2+ pending alterations exist', async () => {
    vi.mocked(api.getPendingAlterations).mockResolvedValue(TWO_PENDING);

    renderWithProviders(<PendingAlterationBanner />);

    const banner = await screen.findByTestId('pending-alteration-banner');
    expect(banner).toHaveTextContent(/2 unresolved Mage Scars/);
  });

  it('renders nothing when logged out and does not call api', async () => {
    renderWithProviders(<PendingAlterationBanner />, false);

    // Give async rendering a tick to settle
    await waitFor(() => {
      expect(screen.queryByTestId('pending-alteration-banner')).not.toBeInTheDocument();
    });

    expect(api.getPendingAlterations).not.toHaveBeenCalled();
  });
});
