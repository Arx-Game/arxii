/**
 * ConversionOfferBanner tests (#2361): mirrors SeanceOfferBanner.test.tsx —
 * hidden when clean, loud when a pending offer exists, fetches for an
 * account with zero available_characters.
 */

import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice } from '@/store/authSlice';
import { ConversionOfferBanner } from './ConversionOfferBanner';
import type { ConversionOffer } from './types';

// Sync vi.mock of './api' — factory hoisted before imports.
vi.mock('./api', () => ({
  getConversionOffers: vi.fn(),
  acceptConversionOffer: vi.fn(),
  declineConversionOffer: vi.fn(),
}));

import * as api from './api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeOffer(overrides: Partial<ConversionOffer> = {}): ConversionOffer {
  return {
    id: 9,
    honoree_name: 'Ariel',
    ceremony_location_name: 'The Old Chapel',
    ceremony_id: 5,
    presented_being_name: 'The Hollow Flame',
    status: 'pending',
    created_at: '2026-08-15T00:00:00Z',
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

describe('ConversionOfferBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the empty sentinel when there are no pending offers', async () => {
    vi.mocked(api.getConversionOffers).mockResolvedValue([]);

    renderWithProviders(<ConversionOfferBanner />);

    expect(await screen.findByTestId('conversion-offer-banner-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('conversion-offer-banner')).not.toBeInTheDocument();
  });

  it('shows a call-out for a pending offer', async () => {
    vi.mocked(api.getConversionOffers).mockResolvedValue([makeOffer()]);

    renderWithProviders(<ConversionOfferBanner />);

    const banner = await screen.findByTestId('conversion-offer-banner');
    expect(banner).toHaveTextContent('Ariel');
    expect(banner).toHaveTextContent('The Old Chapel');
    expect(banner).toHaveTextContent('The Hollow Flame');
  });

  it('renders nothing and does not call the api when logged out', async () => {
    renderWithProviders(<ConversionOfferBanner />, false);

    await waitFor(() => {
      expect(screen.queryByTestId('conversion-offer-banner')).not.toBeInTheDocument();
    });

    expect(api.getConversionOffers).not.toHaveBeenCalled();
  });

  it('still fetches and shows offers for an account with zero available_characters', async () => {
    vi.mocked(api.getConversionOffers).mockResolvedValue([makeOffer()]);

    renderWithProviders(<ConversionOfferBanner />, true, []);

    const banner = await screen.findByTestId('conversion-offer-banner');
    expect(banner).toHaveTextContent('Ariel');
    expect(api.getConversionOffers).toHaveBeenCalled();
  });
});
