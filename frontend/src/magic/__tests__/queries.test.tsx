/**
 * Magic Query Hooks Tests
 *
 * Tests for React Query hooks in the magic module.
 * Covers soul-tether detail, threads, pending sineating, pending stage-advance,
 * and the dissolve + respond-to-sineating mutations.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  useSoulTetherDetail,
  usePendingSineatingOffers,
  usePendingStageAdvanceOffers,
  useThreads,
  useCharacterResonances,
  useDissolveSoulTether,
  useRespondToSineating,
  useThreadHubSummary,
  useThread,
  useTeachingOffers,
  useWeaveThread,
  usePatchThreadNarrative,
  useRetireThread,
  useImbueThread,
  useCrossXPLock,
  useCommitPull,
  useAcceptTeachingOffer,
  magicKeys,
} from '../queries';
import { __resetImbuingRitualIdCacheForTests } from '../api';

// Mock the API module
vi.mock('../api', () => ({
  getSoulTetherDetail: vi.fn(),
  getPendingSineatingOffers: vi.fn(),
  getPendingStageAdvanceOffers: vi.fn(),
  getPendingStageAdvanceOffer: vi.fn(),
  getPendingSineatingOffer: vi.fn(),
  getThreads: vi.fn(),
  getCharacterResonances: vi.fn(),
  dissolveSoulTether: vi.fn(),
  requestSineating: vi.fn(),
  respondToSineating: vi.fn(),
  performRescue: vi.fn(),
  respondToStageAdvance: vi.fn(),
  // New functions for thread spending UI
  getThreadHubSummary: vi.fn(),
  getThread: vi.fn(),
  getTeachingOffers: vi.fn(),
  weaveThread: vi.fn(),
  patchThreadNarrative: vi.fn(),
  retireThread: vi.fn(),
  imbueThreadAuto: vi.fn(),
  crossXPLock: vi.fn(),
  commitPull: vi.fn(),
  acceptTeachingOffer: vi.fn(),
  __resetImbuingRitualIdCacheForTests: vi.fn(),
}));

import * as api from '../api';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockSoulTetherDetail = {
  relationship_id: 42,
  is_soul_tether: true,
  soul_tether_role: 'ABYSSAL',
  sinner_sheet_id: 10,
  sineater_sheet_id: 20,
  hollow_current: 30,
  hollow_max: 50,
  sineater_lifetime_helped: 100,
  sinner_corruption_stage: 2,
  sineater_strain_stage: 0,
};

const mockSineatingOffer = {
  id: 1,
  sinner_sheet_id: 10,
  sinner_persona_name: 'Aelindra',
  scene_id: 5,
  scene_name: 'The Whispering Grove',
  resonance_id: 3,
  units_offered: 5,
  anima_cost_per_unit: 2,
  fatigue_cost_per_unit: 1,
  created_at: '2026-05-01T12:00:00Z',
};

const mockStageAdvanceOffer = {
  id: 2,
  sinner_sheet_id: 10,
  sinner_persona_name: 'Aelindra',
  scene_id: 5,
  scene_name: 'The Whispering Grove',
  resonance_id: 3,
  sinner_corruption_stage: 3,
  commit_units_max: 4,
  strain_cost_per_unit: 1,
  created_at: '2026-05-01T12:00:00Z',
  expires_at: '2026-05-01T13:00:00Z',
};

const mockThread = {
  id: 7,
  owner: 10,
  resonance: 3,
  resonance_name: 'Starfire',
  target_kind: 'RELATIONSHIP_CAPSTONE' as const,
  name: 'Bond of Stars',
  description: '',
  level: 10,
  developed_points: 100,
  retired_at: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const mockResonance = {
  id: 3,
  character_sheet: 10,
  resonance: 3,
  resonance_name: 'Starfire',
  resonance_detail: {
    id: 3,
    name: 'Starfire',
    affinity: 1,
    affinity_name: 'Solar',
    description: 'A bright resonance',
    codex_entry_id: null,
  },
  balance: 50,
  lifetime_earned: 200,
  claimed_at: '2026-01-01T00:00:00Z',
};

// ---------------------------------------------------------------------------
// useSoulTetherDetail
// ---------------------------------------------------------------------------

describe('useSoulTetherDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches tether detail successfully', async () => {
    vi.mocked(api.getSoulTetherDetail).mockResolvedValue(mockSoulTetherDetail);

    const { result } = renderHook(() => useSoulTetherDetail(42), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockSoulTetherDetail);
    expect(api.getSoulTetherDetail).toHaveBeenCalledWith(42);
  });

  it('does not fetch when relationshipId is 0', () => {
    const { result } = renderHook(() => useSoulTetherDetail(0), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getSoulTetherDetail).not.toHaveBeenCalled();
  });

  it('does not fetch when relationshipId is negative', () => {
    const { result } = renderHook(() => useSoulTetherDetail(-1), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getSoulTetherDetail).not.toHaveBeenCalled();
  });

  it('enters error state on fetch failure', async () => {
    vi.mocked(api.getSoulTetherDetail).mockRejectedValue(new Error('Network error'));

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { result } = renderHook(
      () =>
        useQuery({
          queryKey: magicKeys.soulTetherDetail(42),
          queryFn: () => api.getSoulTetherDetail(42),
          retry: false,
        }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).not.toBeNull();

    consoleSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// usePendingSineatingOffers
// ---------------------------------------------------------------------------

describe('usePendingSineatingOffers', () => {
  it('fetches pending sineating offers list', async () => {
    const mockList = { count: 1, next: null, previous: null, results: [mockSineatingOffer] };
    vi.mocked(api.getPendingSineatingOffers).mockResolvedValue(mockList);

    const { result } = renderHook(() => usePendingSineatingOffers(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockList);
    expect(api.getPendingSineatingOffers).toHaveBeenCalledTimes(1);
  });

  it('enters error state on fetch failure', async () => {
    vi.mocked(api.getPendingSineatingOffers).mockRejectedValue(new Error('Unauthorized'));

    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { result } = renderHook(
      () =>
        useQuery({
          queryKey: magicKeys.sineatingPending(),
          queryFn: () => api.getPendingSineatingOffers(),
          retry: false,
        }),
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    consoleSpy.mockRestore();
  });
});

// ---------------------------------------------------------------------------
// usePendingStageAdvanceOffers
// ---------------------------------------------------------------------------

describe('usePendingStageAdvanceOffers', () => {
  it('fetches pending stage-advance offers list', async () => {
    const mockList = { count: 1, next: null, previous: null, results: [mockStageAdvanceOffer] };
    vi.mocked(api.getPendingStageAdvanceOffers).mockResolvedValue(mockList);

    const { result } = renderHook(() => usePendingStageAdvanceOffers(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockList);
    expect(api.getPendingStageAdvanceOffers).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// useThreads
// ---------------------------------------------------------------------------

describe('useThreads', () => {
  it('fetches thread list successfully', async () => {
    const mockList = { count: 1, next: null, previous: null, results: [mockThread] };
    vi.mocked(api.getThreads).mockResolvedValue(mockList);

    const { result } = renderHook(() => useThreads(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockList);
    expect(api.getThreads).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// useCharacterResonances
// ---------------------------------------------------------------------------

describe('useCharacterResonances', () => {
  it('fetches character resonances list', async () => {
    vi.mocked(api.getCharacterResonances).mockResolvedValue([mockResonance]);

    const { result } = renderHook(() => useCharacterResonances(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual([mockResonance]);
    expect(api.getCharacterResonances).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// useDissolveSoulTether
// ---------------------------------------------------------------------------

describe('useDissolveSoulTether', () => {
  it('posts correct dissolve body and succeeds', async () => {
    vi.mocked(api.dissolveSoulTether).mockResolvedValue(undefined);

    const { result } = renderHook(() => useDissolveSoulTether(), {
      wrapper: createWrapper(),
    });

    const body = { actor_sheet_id: 10, relationship_id: 42 };

    await act(async () => {
      await result.current.mutateAsync(body);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.dissolveSoulTether).toHaveBeenCalledWith(body);
  });

  it('surfaces error on failure', async () => {
    vi.mocked(api.dissolveSoulTether).mockRejectedValue(new Error('Not a Soul Tether'));

    const { result } = renderHook(() => useDissolveSoulTether(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      try {
        await result.current.mutateAsync({ actor_sheet_id: 10, relationship_id: 42 });
      } catch {
        // expected
      }
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// useRespondToSineating
// ---------------------------------------------------------------------------

describe('useRespondToSineating', () => {
  it('posts accept response with units_accepted > 0', async () => {
    const mockResult = {
      units_accepted: 3,
      declined: false,
      new_hollow_current: 33,
      new_lifetime_helped: 103,
      audit_row_id: 99,
    };
    vi.mocked(api.respondToSineating).mockResolvedValue(mockResult);

    const { result } = renderHook(() => useRespondToSineating(), {
      wrapper: createWrapper(),
    });

    const body = { sinner_sheet_id: 10, sineater_sheet_id: 20, units_accepted: 3 };

    await act(async () => {
      await result.current.mutateAsync(body);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.respondToSineating).toHaveBeenCalledWith(body);
    expect(result.current.data).toEqual(mockResult);
  });

  it('posts decline response with units_accepted=0', async () => {
    const mockResult = {
      units_accepted: 0,
      declined: true,
      new_hollow_current: 30,
      new_lifetime_helped: 100,
      audit_row_id: 100,
    };
    vi.mocked(api.respondToSineating).mockResolvedValue(mockResult);

    const { result } = renderHook(() => useRespondToSineating(), {
      wrapper: createWrapper(),
    });

    const body = { sinner_sheet_id: 10, sineater_sheet_id: 20, units_accepted: 0 };

    await act(async () => {
      await result.current.mutateAsync(body);
    });

    expect(api.respondToSineating).toHaveBeenCalledWith(body);
  });
});

// ---------------------------------------------------------------------------
// magicKeys factory
// ---------------------------------------------------------------------------

describe('magicKeys', () => {
  it('generates correct query key shapes', () => {
    expect(magicKeys.all).toEqual(['magic']);
    expect(magicKeys.soulTether()).toEqual(['magic', 'soul-tether']);
    expect(magicKeys.soulTetherDetail(42)).toEqual(['magic', 'soul-tether', 'detail', 42]);
    expect(magicKeys.sineatingPending()).toEqual(['magic', 'soul-tether', 'sineating', 'pending']);
    expect(magicKeys.sineatingPendingDetail(5)).toEqual([
      'magic',
      'soul-tether',
      'sineating',
      'pending',
      5,
    ]);
    expect(magicKeys.stageAdvancePending()).toEqual([
      'magic',
      'soul-tether',
      'stage-advance',
      'pending',
    ]);
    expect(magicKeys.stageAdvancePendingDetail(3)).toEqual([
      'magic',
      'soul-tether',
      'stage-advance',
      'pending',
      3,
    ]);
    expect(magicKeys.threadList()).toEqual(['magic', 'threads', 'list']);
    expect(magicKeys.thread(7)).toEqual(['magic', 'threads', 7]);
    expect(magicKeys.threadHubSummary()).toEqual(['magic', 'thread-hub-summary']);
    expect(magicKeys.characterResonanceList()).toEqual(['magic', 'character-resonances', 'list']);
    expect(magicKeys.teachingOffers()).toEqual(['magic', 'teaching-offers', 'list']);
  });
});

// ---------------------------------------------------------------------------
// Fixtures for new hooks
// ---------------------------------------------------------------------------

const mockThreadHubSummary = {
  balances: [{ resonance_id: 3, balance: 50, lifetime_earned: 200, flavor_text: 'Blazing' }],
  ready_thread_ids: [7],
  near_xp_lock_thread_ids: [],
  blocked_thread_ids: [],
  weaving_eligibility: {
    TRAIT: true,
    TECHNIQUE: true,
    ROOM: true,
    RELATIONSHIP_TRACK: true,
    RELATIONSHIP_CAPSTONE: true,
    FACET: true,
    COVENANT_ROLE: false,
  },
};

const mockTeachingOffer = {
  id: 1,
  teacher: 5,
  unlock: 10,
  unlock_target_kind: 'TRAIT',
  unlock_display_name: 'Fire Shaping',
  unlock_xp_cost: 4,
  effective_xp_cost_for_viewer: 3,
  pitch: 'Let me show you the flame.',
  gold_cost: 0,
};

// mockThread is already defined in the file above
const mockWeaveBody = {
  resonance: 3,
  target_kind: 'TRAIT' as const,
  target_id: 1,
  character_sheet_id: 10,
};

// ---------------------------------------------------------------------------
// useThreadHubSummary
// ---------------------------------------------------------------------------

describe('useThreadHubSummary', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches thread hub summary successfully', async () => {
    vi.mocked(api.getThreadHubSummary).mockResolvedValue(mockThreadHubSummary);

    const { result } = renderHook(() => useThreadHubSummary(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockThreadHubSummary);
    expect(api.getThreadHubSummary).toHaveBeenCalledWith(undefined);
  });

  it('passes characterSheetId when provided', async () => {
    vi.mocked(api.getThreadHubSummary).mockResolvedValue(mockThreadHubSummary);

    const { result } = renderHook(() => useThreadHubSummary(99), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.getThreadHubSummary).toHaveBeenCalledWith(99);
  });
});

// ---------------------------------------------------------------------------
// useThread
// ---------------------------------------------------------------------------

describe('useThread', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches thread by id', async () => {
    vi.mocked(api.getThread).mockResolvedValue(mockThread);

    const { result } = renderHook(() => useThread(7), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockThread);
    expect(api.getThread).toHaveBeenCalledWith(7);
  });

  it('is disabled when id is 0', () => {
    const { result } = renderHook(() => useThread(0), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getThread).not.toHaveBeenCalled();
  });

  it('is disabled when id is negative', () => {
    const { result } = renderHook(() => useThread(-1), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getThread).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// useTeachingOffers
// ---------------------------------------------------------------------------

describe('useTeachingOffers', () => {
  it('fetches teaching offers list', async () => {
    const mockList = { count: 1, next: null, previous: null, results: [mockTeachingOffer] };
    vi.mocked(api.getTeachingOffers).mockResolvedValue(mockList);

    const { result } = renderHook(() => useTeachingOffers(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockList);
    expect(api.getTeachingOffers).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// useWeaveThread
// ---------------------------------------------------------------------------

describe('useWeaveThread', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls weaveThread with correct body and succeeds', async () => {
    vi.mocked(api.weaveThread).mockResolvedValue(mockThread);

    const { result } = renderHook(() => useWeaveThread(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync(mockWeaveBody);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.weaveThread).toHaveBeenCalledWith(mockWeaveBody);
    expect(result.current.data).toEqual(mockThread);
  });

  it('surfaces error on failure', async () => {
    vi.mocked(api.weaveThread).mockRejectedValue(new Error('Thread limit reached'));

    const { result } = renderHook(() => useWeaveThread(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      try {
        await result.current.mutateAsync(mockWeaveBody);
      } catch {
        // expected
      }
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// usePatchThreadNarrative
// ---------------------------------------------------------------------------

describe('usePatchThreadNarrative', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('patches thread narrative and succeeds', async () => {
    vi.mocked(api.patchThreadNarrative).mockResolvedValue(mockThread);

    const { result } = renderHook(() => usePatchThreadNarrative(7), {
      wrapper: createWrapper(),
    });

    const patchBody = { name: 'Renamed Thread' };

    await act(async () => {
      await result.current.mutateAsync(patchBody);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.patchThreadNarrative).toHaveBeenCalledWith(7, patchBody);
  });
});

// ---------------------------------------------------------------------------
// useRetireThread
// ---------------------------------------------------------------------------

describe('useRetireThread', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('retires thread and succeeds', async () => {
    vi.mocked(api.retireThread).mockResolvedValue(undefined);

    const { result } = renderHook(() => useRetireThread(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync(7);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.retireThread).toHaveBeenCalledWith(7);
  });
});

// ---------------------------------------------------------------------------
// useImbueThread
// ---------------------------------------------------------------------------

describe('useImbueThread', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    __resetImbuingRitualIdCacheForTests();
  });

  it('calls imbueThreadAuto with correct args', async () => {
    vi.mocked(api.imbueThreadAuto).mockResolvedValue({ success: true });

    const { result } = renderHook(() => useImbueThread(), {
      wrapper: createWrapper(),
    });

    const vars = { characterSheetId: 10, threadId: 7, amount: 5 };

    await act(async () => {
      await result.current.mutateAsync(vars);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.imbueThreadAuto).toHaveBeenCalledWith(10, 7, 5);
  });

  it('surfaces error on failure', async () => {
    vi.mocked(api.imbueThreadAuto).mockRejectedValue(new Error('Insufficient resonance'));

    const { result } = renderHook(() => useImbueThread(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      try {
        await result.current.mutateAsync({ characterSheetId: 10, threadId: 7, amount: 5 });
      } catch {
        // expected
      }
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});

// ---------------------------------------------------------------------------
// useCrossXPLock
// ---------------------------------------------------------------------------

describe('useCrossXPLock', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('calls crossXPLock with correct args', async () => {
    vi.mocked(api.crossXPLock).mockResolvedValue(mockThread);

    const { result } = renderHook(() => useCrossXPLock(), {
      wrapper: createWrapper(),
    });

    const vars = { threadId: 7, body: { character_sheet_id: 10, resonance: 3 } };

    await act(async () => {
      await result.current.mutateAsync(vars);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.crossXPLock).toHaveBeenCalledWith(7, vars.body);
  });
});

// ---------------------------------------------------------------------------
// useCommitPull
// ---------------------------------------------------------------------------

describe('useCommitPull', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('commits pull with correct body and succeeds', async () => {
    const mockResponse = {
      resonance_spent: 10,
      anima_spent: 2,
      resolved_effects: [],
    };
    vi.mocked(api.commitPull).mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useCommitPull(), {
      wrapper: createWrapper(),
    });

    const body = {
      character_sheet_id: 10,
      resonance_id: 3,
      tier: 1 as const,
      thread_ids: [7],
    };

    await act(async () => {
      await result.current.mutateAsync(body);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.commitPull).toHaveBeenCalledWith(body);
    expect(result.current.data).toEqual(mockResponse);
  });
});

// ---------------------------------------------------------------------------
// useAcceptTeachingOffer
// ---------------------------------------------------------------------------

describe('useAcceptTeachingOffer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('accepts offer with offerId and optional body', async () => {
    vi.mocked(api.acceptTeachingOffer).mockResolvedValue(mockTeachingOffer);

    const { result } = renderHook(() => useAcceptTeachingOffer(), {
      wrapper: createWrapper(),
    });

    const vars = { offerId: 1, body: { learner_sheet_id: 10 } };

    await act(async () => {
      await result.current.mutateAsync(vars);
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.acceptTeachingOffer).toHaveBeenCalledWith(1, { learner_sheet_id: 10 });
  });

  it('accepts offer without optional body', async () => {
    vi.mocked(api.acceptTeachingOffer).mockResolvedValue(mockTeachingOffer);

    const { result } = renderHook(() => useAcceptTeachingOffer(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ offerId: 1 });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(api.acceptTeachingOffer).toHaveBeenCalledWith(1, undefined);
  });
});
