/**
 * Tests for Audere offer query hooks (#873).
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice } from '@/store/authSlice';
import { usePendingAudereOffers, useRespondToAudere, magicKeys } from '../queries';
import type { PaginatedPendingAudereOfferList, AudereOfferResult } from '../types';

// Mock only the two api functions this file exercises.
vi.mock('../api', () => ({
  getPendingAudereOffers: vi.fn(),
  respondToAudere: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PENDING_FIXTURE: PaginatedPendingAudereOfferList = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 5,
      character_sheet_id: 3,
      character_name: 'Velenosa',
      fired_intensity: 14,
      soulfray_stage_order: 2,
      intensity_bonus: 2,
      anima_pool_bonus: 10,
      advisory_text: '',
      created_at: '2026-06-01T00:00:00Z',
    },
  ],
};

const RESULT_FIXTURE: AudereOfferResult = {
  accepted: true,
  intensity_bonus_applied: 2,
  anima_pool_expanded_by: 10,
  advisory_text: '',
};

// ---------------------------------------------------------------------------
// Wrapper helpers
// ---------------------------------------------------------------------------

function createAuthStore() {
  const store = configureStore({
    reducer: {
      auth: authSlice.reducer,
    },
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

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const store = createAuthStore();

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </Provider>
    );
  };
}

/**
 * Like createWrapper but returns the QueryClient alongside the wrapper so
 * tests can spy on invalidateQueries after a mutation.
 */
function createWrapperWithClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const store = createAuthStore();

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </Provider>
    );
  }

  return { wrapper: Wrapper, client };
}

// ---------------------------------------------------------------------------
// usePendingAudereOffers
// ---------------------------------------------------------------------------

describe('usePendingAudereOffers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the pending Audere offer list when enabled (default)', async () => {
    vi.mocked(api.getPendingAudereOffers).mockResolvedValue(PENDING_FIXTURE);

    const { result } = renderHook(() => usePendingAudereOffers(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.results?.[0]?.character_name).toBe('Velenosa');
    expect(api.getPendingAudereOffers).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when enabled=false', () => {
    const { result } = renderHook(() => usePendingAudereOffers(false), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getPendingAudereOffers).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useRespondToAudere
// ---------------------------------------------------------------------------

describe('useRespondToAudere', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes the payload through to api.respondToAudere', async () => {
    vi.mocked(api.respondToAudere).mockResolvedValue(RESULT_FIXTURE);

    const { result } = renderHook(() => useRespondToAudere(3, 11), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ offer_id: 5, accept: true });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.respondToAudere).toHaveBeenCalledWith({ offer_id: 5, accept: true });
  });

  it('invalidates the inbox, anima, and encounter queries on success', async () => {
    vi.mocked(api.respondToAudere).mockResolvedValue(RESULT_FIXTURE);

    const { wrapper, client } = createWrapperWithClient();
    // gcTime: 0 evicts an unobserved cache entry on a timer tick, so asserting
    // isInvalidated on a seeded entry races the GC — assert the call instead.
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useRespondToAudere(3, 11), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ offer_id: 5, accept: false });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['magic', 'audere', 'pending'],
      });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['magic', 'character-anima', 3],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['combat', 'encounter', 11],
    });
  });
});

// ---------------------------------------------------------------------------
// magicKeys factory — Audere key shape
// ---------------------------------------------------------------------------

describe('magicKeys — Audere keys', () => {
  it('auderePending() equals [magic, audere, pending]', () => {
    expect(magicKeys.auderePending()).toEqual(['magic', 'audere', 'pending']);
  });
});
