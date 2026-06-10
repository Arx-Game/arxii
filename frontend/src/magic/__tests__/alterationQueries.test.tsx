/**
 * Tests for pending-alteration query hooks (#877).
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice } from '@/store/authSlice';
import {
  usePendingAlterations,
  useAlterationLibrary,
  useResolveAlteration,
  magicKeys,
} from '../queries';
import type { PaginatedPendingAlterationList } from '../types';

// Mock only the four api functions this file exercises.
// AlterationResolveError is inlined in the factory so it is available at
// hoist time (vi.mock factories are hoisted before class declarations).
vi.mock('../api', () => ({
  getPendingAlterations: vi.fn(),
  getAlterationLibrary: vi.fn(),
  resolveAlteration: vi.fn(),
  // AlterationResolveError inlined so instanceof checks keep working even
  // though vi.mock factories are hoisted before class declarations.
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

const PENDING_FIXTURE: PaginatedPendingAlterationList = {
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

function createWrapper(authenticated = true) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const store = createAuthStore(authenticated);

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
 * tests can inspect cache state (e.g. isInvalidated) after a mutation.
 */
function createWrapperWithClient(authenticated = true) {
  const client = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });
  const store = createAuthStore(authenticated);

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
// usePendingAlterations
// ---------------------------------------------------------------------------

describe('usePendingAlterations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the pending alteration list when logged in', async () => {
    vi.mocked(api.getPendingAlterations).mockResolvedValue(PENDING_FIXTURE);

    const { result } = renderHook(() => usePendingAlterations(), {
      wrapper: createWrapper(true),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.results?.[0]?.character_name).toBe('Velenosa');
    expect(api.getPendingAlterations).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when logged out', () => {
    const { result } = renderHook(() => usePendingAlterations(), {
      wrapper: createWrapper(false),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getPendingAlterations).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useAlterationLibrary
// ---------------------------------------------------------------------------

describe('useAlterationLibrary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches library entries for the given pendingId and calls api with 7', async () => {
    const mockLibrary = [
      {
        id: 11,
        name: 'Shadow Touch',
        tier: 3 as const,
        player_description: 'A subtle mark.',
        observer_description: 'Subtle shadow.',
        origin_affinity_name: 'Abyssal',
        weakness_magnitude: 0,
        resonance_bonus_magnitude: 1,
        social_reactivity_magnitude: 0,
        is_visible_at_rest: false,
      },
    ];
    vi.mocked(api.getAlterationLibrary).mockResolvedValue(mockLibrary);

    const { result } = renderHook(() => useAlterationLibrary(7), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.getAlterationLibrary).toHaveBeenCalledWith(7);
    expect(result.current.data).toEqual(mockLibrary);
  });

  it('does not call the api when pendingId is null', () => {
    const { result } = renderHook(() => useAlterationLibrary(null), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getAlterationLibrary).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useResolveAlteration
// ---------------------------------------------------------------------------

describe('useResolveAlteration', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls resolveAlteration with pendingId and payload on mutate', async () => {
    vi.mocked(api.resolveAlteration).mockResolvedValue({ status: 'resolved', event_id: 42 });

    const { result } = renderHook(() => useResolveAlteration(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ pendingId: 7, payload: { library_template_id: 11 } });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.resolveAlteration).toHaveBeenCalledWith(7, { library_template_id: 11 });
  });

  it('invalidates the pending-alterations query after a successful resolve', async () => {
    vi.mocked(api.resolveAlteration).mockResolvedValue({ status: 'resolved', event_id: 42 });

    const { wrapper, client } = createWrapperWithClient();

    // Seed the pending-alterations cache so its query state is trackable.
    client.setQueryData(['magic', 'pending-alterations'], PENDING_FIXTURE);

    const { result } = renderHook(() => useResolveAlteration(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ pendingId: 7, payload: { library_template_id: 11 } });
    });

    // The query has no active observer so it stays invalidated rather than
    // auto-refetching — assert the cache entry is marked stale/invalid.
    await waitFor(() => {
      expect(client.getQueryState(['magic', 'pending-alterations'])?.isInvalidated).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// magicKeys factory — pending alteration key shapes
// ---------------------------------------------------------------------------

describe('magicKeys — alteration keys', () => {
  it('pendingAlterations() equals [magic, pending-alterations]', () => {
    expect(magicKeys.pendingAlterations()).toEqual(['magic', 'pending-alterations']);
  });

  it('alterationLibrary(7) equals [magic, pending-alterations, library, 7]', () => {
    expect(magicKeys.alterationLibrary(7)).toEqual(['magic', 'pending-alterations', 'library', 7]);
  });
});
