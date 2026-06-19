/**
 * useCastPullSelection — unit tests
 *
 * Mocks ``useThreads`` and ``useCharacterResonances`` from ``@/magic/queries``
 * to avoid network/query-client overhead. Uses ``renderHook`` + ``act`` from
 * @testing-library/react, mirroring the style in useThreading.test.ts and
 * src/magic/__tests__/queries.test.tsx.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { createElement } from 'react';
import { useCastPullSelection } from '../useCastPullSelection';

// ---------------------------------------------------------------------------
// Mock @/magic/queries so no real network calls are made.
// ---------------------------------------------------------------------------

vi.mock('@/magic/queries', () => ({
  useThreads: vi.fn(),
  useCharacterResonances: vi.fn(),
}));

import { useThreads, useCharacterResonances } from '@/magic/queries';

const mockUseThreads = vi.mocked(useThreads);
const mockUseCharacterResonances = vi.mocked(useCharacterResonances);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

/**
 * Three test threads:
 *   id=1 → resonance 10
 *   id=2 → resonance 10  (same resonance as thread 1)
 *   id=3 → resonance 20  (different resonance)
 */
const THREAD_1 = { id: 1, resonance: 10, name: 'Alpha' };
const THREAD_2 = { id: 2, resonance: 10, name: 'Beta' };
const THREAD_3 = { id: 3, resonance: 20, name: 'Gamma' };

function setupThreads(threads = [THREAD_1, THREAD_2, THREAD_3]) {
  mockUseThreads.mockReturnValue({
    data: { results: threads },
    isLoading: false,
  } as ReturnType<typeof useThreads>);
}

function setupResonances(
  resonances: Array<{ resonance: number; balance: number }> = [
    { resonance: 10, balance: 5 },
    { resonance: 20, balance: 3 },
  ]
) {
  mockUseCharacterResonances.mockReturnValue({
    data: resonances,
    isLoading: false,
  } as ReturnType<typeof useCharacterResonances>);
}

const baseParams = {
  selectedTechnique: { id: 42, name: 'Flamecall', strain_cost: 1 } as Parameters<
    typeof useCastPullSelection
  >[0]['selectedTechnique'],
  characterId: 7,
  castTargetPersonaId: null,
  sceneId: '99',
  castOpen: true,
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  setupThreads();
  setupResonances();
});

describe('useCastPullSelection', () => {
  // -------------------------------------------------------------------------
  // Case 1: grouping revert + notice
  // -------------------------------------------------------------------------
  describe('handlePullsChange — single (resonance, tier) group enforcement', () => {
    it('reverts conflicting paid pulls to one (resonance, tier) group', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      // Raise thread 1 at tier 2 first
      act(() => result.current.handlePullsChange({ 1: 2, 2: 0, 3: 0 }));
      expect(result.current.selectedPulls).toEqual({ 1: 2, 2: 0, 3: 0 });

      // Newly raise thread 3 (different resonance 20) — thread 3 is the anchor,
      // thread 1 (resonance 10) disagrees so thread 1 is reverted.
      act(() => result.current.handlePullsChange({ 1: 2, 2: 0, 3: 2 }));
      expect(result.current.selectedPulls).toEqual({ 1: 0, 2: 0, 3: 2 });
      expect(result.current.pullNotice).toMatch(/single resonance and tier/i);
    });

    it('reverts pulls with a different tier in the same resonance', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      // Thread 1 at tier 2 (resonance 10)
      act(() => result.current.handlePullsChange({ 1: 2, 2: 0, 3: 0 }));
      // Thread 2 (same resonance 10) newly raised at tier 3 — different tier.
      // Thread 2 is the anchor; thread 1 disagrees on tier so thread 1 is reverted.
      act(() => result.current.handlePullsChange({ 1: 2, 2: 3, 3: 0 }));
      expect(result.current.selectedPulls).toEqual({ 1: 0, 2: 3, 3: 0 });
      expect(result.current.pullNotice).toMatch(/single resonance and tier/i);
    });

    it('allows same resonance and same tier to coexist', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      // Thread 1 at tier 2
      act(() => result.current.handlePullsChange({ 1: 2, 2: 0, 3: 0 }));
      // Thread 2 (same resonance 10, same tier 2) — no conflict
      act(() => result.current.handlePullsChange({ 1: 2, 2: 2, 3: 0 }));
      expect(result.current.selectedPulls).toEqual({ 1: 2, 2: 2, 3: 0 });
      expect(result.current.pullNotice).toBeNull();
    });

    it('clears pullNotice when all paid pulls are deselected', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      // Create a conflict to set a notice
      act(() => result.current.handlePullsChange({ 1: 2, 2: 0, 3: 0 }));
      act(() => result.current.handlePullsChange({ 1: 2, 2: 0, 3: 2 }));
      expect(result.current.pullNotice).not.toBeNull();

      // Deselect all
      act(() => result.current.handlePullsChange({ 1: 0, 2: 0, 3: 0 }));
      expect(result.current.pullNotice).toBeNull();
    });
  });

  // -------------------------------------------------------------------------
  // Case 2: unresolved resonance passes through unconstrained
  // -------------------------------------------------------------------------
  describe('handlePullsChange — unresolved thread resonance', () => {
    it('passes through unconstrained when the changed thread is not in the cache', () => {
      // Only threads 1 and 2 in cache — thread 99 is unknown
      setupThreads([THREAD_1, THREAD_2]);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      // Thread 1 at tier 2 first
      act(() => result.current.handlePullsChange({ 1: 2 }));
      // Thread 99 not in cache — pass through without reverting thread 1
      act(() => result.current.handlePullsChange({ 1: 2, 99: 2 }));
      expect(result.current.selectedPulls).toEqual({ 1: 2, 99: 2 });
    });
  });

  // -------------------------------------------------------------------------
  // Case 3: buildPullPayload — paid / none
  // -------------------------------------------------------------------------
  describe('buildPullPayload', () => {
    it('returns { pull } with correct fields for paid pulls sharing a group', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      act(() => result.current.handlePullsChange({ 1: 2, 2: 2, 3: 0 }));
      const payload = result.current.buildPullPayload();
      expect(payload).toEqual({
        pull: {
          resonance_id: 10,
          tier: 2,
          thread_ids: [1, 2],
        },
      });
    });

    it('returns {} when no paid pulls are selected', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      // Leave all at tier 0
      const payload = result.current.buildPullPayload();
      expect(payload).toEqual({});
    });

    // -----------------------------------------------------------------------
    // Case 4: buildPullPayload error when thread not in cache
    // -----------------------------------------------------------------------
    it('returns { error } when the first paid thread is not in the resolved cache', () => {
      // Empty thread cache
      setupThreads([]);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      // Manually set selectedPulls via handlePullsChange on a thread not in cache
      // Since thread 99 is not in cache, the changed-thread resonance is undefined
      // and the selection passes through unconstrained.
      act(() => result.current.handlePullsChange({ 99: 1 }));
      expect(result.current.selectedPulls).toEqual({ 99: 1 });

      const payload = result.current.buildPullPayload();
      expect('error' in payload).toBe(true);
      expect((payload as { error: string }).error).toMatch(/still loading/i);
    });
  });

  // -------------------------------------------------------------------------
  // Case 5: balanceByResonanceId mapping
  // -------------------------------------------------------------------------
  describe('balanceByResonanceId', () => {
    it('maps resonance id to balance from useCharacterResonances', () => {
      setupResonances([
        { resonance: 10, balance: 7 },
        { resonance: 20, balance: 2 },
      ]);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });
      expect(result.current.balanceByResonanceId).toEqual({ 10: 7, 20: 2 });
    });

    it('returns {} when resonances data is not yet available', () => {
      mockUseCharacterResonances.mockReturnValue({
        data: undefined,
        isLoading: true,
      } as ReturnType<typeof useCharacterResonances>);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });
      expect(result.current.balanceByResonanceId).toEqual({});
    });
  });

  // -------------------------------------------------------------------------
  // Case 6: pullsContext gating
  // -------------------------------------------------------------------------
  describe('pullsContext', () => {
    it('is null when castOpen is false', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(
        () => useCastPullSelection({ ...baseParams, castOpen: false }),
        { wrapper }
      );
      expect(result.current.pullsContext).toBeNull();
    });

    it('is null when selectedTechnique is null', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(
        () => useCastPullSelection({ ...baseParams, selectedTechnique: null }),
        { wrapper }
      );
      expect(result.current.pullsContext).toBeNull();
    });

    it('is null when characterId is null', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(
        () => useCastPullSelection({ ...baseParams, characterId: null }),
        { wrapper }
      );
      expect(result.current.pullsContext).toBeNull();
    });

    it('is populated when castOpen && selectedTechnique && characterId !== null', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });
      expect(result.current.pullsContext).toEqual({
        character_sheet_id: 7,
        technique_id: 42,
        target_persona_id: null,
        scene_id: 99,
      });
    });
  });

  // -------------------------------------------------------------------------
  // reset()
  // -------------------------------------------------------------------------
  describe('reset', () => {
    it('clears selectedPulls and pullNotice', () => {
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCastPullSelection(baseParams), { wrapper });

      act(() => result.current.handlePullsChange({ 1: 2, 3: 2 }));
      // Force a notice by triggering a conflict
      act(() => result.current.setPullNotice('some notice'));
      act(() => result.current.reset());

      expect(result.current.selectedPulls).toEqual({});
      expect(result.current.pullNotice).toBeNull();
    });
  });
});
