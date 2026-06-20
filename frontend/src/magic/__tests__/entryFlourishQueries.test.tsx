/**
 * Tests for entry-flourish offer query hooks (#1140).
 * Mirrors the audereQueries.test.tsx pattern: vi.fn() mocks, no msw.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice } from '@/store/authSlice';
import { usePendingEntryFlourishOffers, useRespondToEntryFlourish, magicKeys } from '../queries';
import type { PaginatedPendingEntryFlourishOfferList, EntryFlourishResult } from '../types';

// Mock only the two api functions this file exercises.
vi.mock('../api', () => ({
  getPendingEntryFlourishOffers: vi.fn(),
  respondToEntryFlourish: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PENDING_FIXTURE: PaginatedPendingEntryFlourishOfferList = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 9,
      character_sheet_id: 4,
      scene_id: 101,
      created_at: '2026-06-15T00:00:00Z',
    },
  ],
};

const RESULT_FIXTURE: EntryFlourishResult = {
  resonance_id: 7,
  resonance_name: 'Ember',
  granted_amount: 5,
  scene_id: 101,
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
// usePendingEntryFlourishOffers
// ---------------------------------------------------------------------------

describe('usePendingEntryFlourishOffers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the pending entry-flourish offer list when enabled (default)', async () => {
    vi.mocked(api.getPendingEntryFlourishOffers).mockResolvedValue(PENDING_FIXTURE);

    const { result } = renderHook(() => usePendingEntryFlourishOffers(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.results?.[0]?.character_sheet_id).toBe(4);
    expect(api.getPendingEntryFlourishOffers).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when enabled=false', () => {
    const { result } = renderHook(() => usePendingEntryFlourishOffers(false), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getPendingEntryFlourishOffers).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useRespondToEntryFlourish
// ---------------------------------------------------------------------------

describe('useRespondToEntryFlourish', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes the payload through to api.respondToEntryFlourish', async () => {
    vi.mocked(api.respondToEntryFlourish).mockResolvedValue(RESULT_FIXTURE);

    const { result } = renderHook(() => useRespondToEntryFlourish(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ offer_id: 9, resonance_id: 7 });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.respondToEntryFlourish).toHaveBeenCalledWith({ offer_id: 9, resonance_id: 7 });
  });

  it('invalidates the entryFlourishPending query key on success', async () => {
    vi.mocked(api.respondToEntryFlourish).mockResolvedValue(RESULT_FIXTURE);

    const { wrapper, client } = createWrapperWithClient();
    // gcTime: 0 evicts unobserved cache entries; assert the call instead.
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useRespondToEntryFlourish(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ offer_id: 9, resonance_id: 7 });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['magic', 'entry-flourish', 'pending'],
      });
    });
  });
});

// ---------------------------------------------------------------------------
// magicKeys factory — entry-flourish key shape
// ---------------------------------------------------------------------------

describe('magicKeys — entry-flourish keys', () => {
  it('entryFlourishPending() equals [magic, entry-flourish, pending]', () => {
    expect(magicKeys.entryFlourishPending()).toEqual(['magic', 'entry-flourish', 'pending']);
  });
});
