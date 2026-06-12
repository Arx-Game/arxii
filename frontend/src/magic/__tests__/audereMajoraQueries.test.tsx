/**
 * Tests for Audere Majora query hooks (#543).
 * Mirrors the audereQueries.test.tsx pattern: vi.fn() mocks, no msw.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { authSlice } from '@/store/authSlice';
import {
  usePendingAudereMajoraOffers,
  useRespondToAudereMajora,
  usePathIntent,
  useDeclarePathIntent,
  useClearPathIntent,
  magicKeys,
} from '../queries';
import type {
  PaginatedPendingAudereMajoraOfferList,
  AudereMajoraCrossingResult,
  PathIntentResponse,
} from '../types';

// Mock only the api functions this file exercises.
vi.mock('../api', () => ({
  getPendingAudereMajoraOffers: vi.fn(),
  respondToAudereMajora: vi.fn(),
  getPathIntent: vi.fn(),
  putPathIntent: vi.fn(),
  deletePathIntent: vi.fn(),
}));

import * as api from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ELIGIBLE_PATH = {
  id: 1,
  name: 'Path of Fire',
  stage: 3,
  stage_display: 'Ascendant',
  description: 'A path of burning clarity.',
};

const PENDING_FIXTURE: PaginatedPendingAudereMajoraOfferList = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 7,
      character_sheet_id: 3,
      character_name: 'Velenosa',
      fired_intensity: 18,
      soulfray_stage_order: 3,
      boundary_level: 5,
      target_stage_display: 'Ascendant',
      vision_text: '[TEST VISION]',
      advisory_text: '',
      risk_text: '',
      eligible_paths: [ELIGIBLE_PATH],
      intended_path_id: null,
      created_at: '2026-06-01T00:00:00Z',
    },
  ],
};

const CROSSING_RESULT_FIXTURE: AudereMajoraCrossingResult = {
  accepted: true,
  level_before: 5,
  level_after: 6,
  chosen_path_name: 'Path of Fire',
  advisory_text: '',
  declaration_interaction_id: 42,
};

const PATH_INTENT_FIXTURE: PathIntentResponse = {
  intent: {
    id: 10,
    intended_path: { ...ELIGIBLE_PATH },
    declared_at: '2026-06-01T00:00:00Z',
  },
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
      queries: { retry: false, gcTime: 0 },
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

function createWrapperWithClient() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
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
// usePendingAudereMajoraOffers
// ---------------------------------------------------------------------------

describe('usePendingAudereMajoraOffers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the pending Audere Majora offer list when enabled (default)', async () => {
    vi.mocked(api.getPendingAudereMajoraOffers).mockResolvedValue(PENDING_FIXTURE);

    const { result } = renderHook(() => usePendingAudereMajoraOffers(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.results?.[0]?.character_name).toBe('Velenosa');
    expect(result.current.data?.results?.[0]?.vision_text).toBe('[TEST VISION]');
    expect(api.getPendingAudereMajoraOffers).toHaveBeenCalledTimes(1);
  });

  it('does not fetch when enabled=false', () => {
    const { result } = renderHook(() => usePendingAudereMajoraOffers(false), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getPendingAudereMajoraOffers).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useRespondToAudereMajora
// ---------------------------------------------------------------------------

describe('useRespondToAudereMajora', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('passes the exact payload through to api.respondToAudereMajora', async () => {
    vi.mocked(api.respondToAudereMajora).mockResolvedValue(CROSSING_RESULT_FIXTURE);

    const { result } = renderHook(() => useRespondToAudereMajora(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({
        offer_id: 7,
        accept: true,
        path_id: 1,
        declaration_text: 'I cross the threshold freely.',
      });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.respondToAudereMajora).toHaveBeenCalledWith({
      offer_id: 7,
      accept: true,
      path_id: 1,
      declaration_text: 'I cross the threshold freely.',
    });
  });

  it('invalidates audereMajoraPending, auderePending, and pathIntent on success', async () => {
    vi.mocked(api.respondToAudereMajora).mockResolvedValue(CROSSING_RESULT_FIXTURE);

    const { wrapper, client } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useRespondToAudereMajora(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ offer_id: 7, accept: false });
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['magic', 'audere-majora', 'pending'],
      });
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['magic', 'audere', 'pending'],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['magic', 'path-intent'],
    });
  });
});

// ---------------------------------------------------------------------------
// usePathIntent
// ---------------------------------------------------------------------------

describe('usePathIntent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches the path intent', async () => {
    vi.mocked(api.getPathIntent).mockResolvedValue(PATH_INTENT_FIXTURE);

    const { result } = renderHook(() => usePathIntent(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.intent?.intended_path.name).toBe('Path of Fire');
    expect(api.getPathIntent).toHaveBeenCalledTimes(1);
  });

  it('returns null intent when none is declared', async () => {
    vi.mocked(api.getPathIntent).mockResolvedValue({ intent: null });

    const { result } = renderHook(() => usePathIntent(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.intent).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// useDeclarePathIntent
// ---------------------------------------------------------------------------

describe('useDeclarePathIntent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls api.putPathIntent with the given path id', async () => {
    vi.mocked(api.putPathIntent).mockResolvedValue(PATH_INTENT_FIXTURE);

    const { result } = renderHook(() => useDeclarePathIntent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync(1);
    });

    expect(api.putPathIntent).toHaveBeenCalledWith(1);
  });

  it('invalidates pathIntent on success', async () => {
    vi.mocked(api.putPathIntent).mockResolvedValue(PATH_INTENT_FIXTURE);

    const { wrapper, client } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useDeclarePathIntent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(1);
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['magic', 'path-intent'],
      });
    });
  });
});

// ---------------------------------------------------------------------------
// useClearPathIntent
// ---------------------------------------------------------------------------

describe('useClearPathIntent', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls api.deletePathIntent', async () => {
    vi.mocked(api.deletePathIntent).mockResolvedValue(undefined);

    const { result } = renderHook(() => useClearPathIntent(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(api.deletePathIntent).toHaveBeenCalledTimes(1);
  });

  it('invalidates pathIntent on success', async () => {
    vi.mocked(api.deletePathIntent).mockResolvedValue(undefined);

    const { wrapper, client } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const { result } = renderHook(() => useClearPathIntent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync();
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ['magic', 'path-intent'],
      });
    });
  });
});

// ---------------------------------------------------------------------------
// magicKeys factory — Audere Majora + PathIntent key shapes
// ---------------------------------------------------------------------------

describe('magicKeys — Audere Majora + PathIntent keys', () => {
  it('audereMajoraPending() equals [magic, audere-majora, pending]', () => {
    expect(magicKeys.audereMajoraPending()).toEqual(['magic', 'audere-majora', 'pending']);
  });

  it('pathIntent() equals [magic, path-intent]', () => {
    expect(magicKeys.pathIntent()).toEqual(['magic', 'path-intent']);
  });
});
