/**
 * SeanceOfferBanner tests (#2393): hidden when clean, loud when a pending
 * offer exists — and, per the deliberate divergence from
 * usePendingAlterations, still loud for a zero-available_characters
 * account (the retired-only honoree case this banner exists for).
 */

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice } from '@/store/authSlice';
import { SeanceOfferBanner } from './SeanceOfferBanner';
import type { SeanceOffer } from './types';

// Sync vi.mock of './api' — factory hoisted before imports.
vi.mock('./api', () => ({
  getSeanceOffers: vi.fn(),
  acceptSeanceOffer: vi.fn(),
  declineSeanceOffer: vi.fn(),
}));

import * as api from './api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeOffer(overrides: Partial<SeanceOffer> = {}): SeanceOffer {
  return {
    id: 7,
    honoree_name: 'Ariel',
    ceremony_location_name: 'The Old Chapel',
    ceremony_id: 3,
    status: 'pending',
    created_at: '2026-07-19T00:00:00Z',
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Wrapper helpers
// ---------------------------------------------------------------------------

function createAuthStore(authenticated: boolean, availableCharacters: unknown[] = []) {
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
        available_characters: availableCharacters,
      } as Parameters<typeof authSlice.actions.setAccount>[0])
    );
  }

  return store;
}

function renderWithProviders(
  ui: ReactNode,
  authenticated = true,
  availableCharacters: unknown[] = []
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
  const store = createAuthStore(authenticated, availableCharacters);

  return render(
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </Provider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SeanceOfferBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the empty sentinel when there are no pending offers', async () => {
    vi.mocked(api.getSeanceOffers).mockResolvedValue([]);

    renderWithProviders(<SeanceOfferBanner />);

    expect(await screen.findByTestId('seance-offer-banner-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('seance-offer-banner')).not.toBeInTheDocument();
  });

  it('shows a call-out for a pending offer', async () => {
    vi.mocked(api.getSeanceOffers).mockResolvedValue([makeOffer()]);

    renderWithProviders(<SeanceOfferBanner />);

    const banner = await screen.findByTestId('seance-offer-banner');
    expect(banner).toHaveTextContent('Ariel');
    expect(banner).toHaveTextContent('The Old Chapel');
  });

  it('renders nothing and does not call the api when logged out', async () => {
    renderWithProviders(<SeanceOfferBanner />, false);

    await waitFor(() => {
      expect(screen.queryByTestId('seance-offer-banner')).not.toBeInTheDocument();
    });

    expect(api.getSeanceOffers).not.toHaveBeenCalled();
  });

  it('still fetches and shows offers for an account with zero available_characters', async () => {
    // The deliberate divergence from usePendingAlterations: a retired-only
    // honoree's account has no available_characters, and is exactly who
    // most needs to see this banner.
    vi.mocked(api.getSeanceOffers).mockResolvedValue([makeOffer()]);

    renderWithProviders(<SeanceOfferBanner />, true, []);

    const banner = await screen.findByTestId('seance-offer-banner');
    expect(banner).toHaveTextContent('Ariel');
    expect(api.getSeanceOffers).toHaveBeenCalled();
  });
});
