/**
 * Character Creation Query Hooks Tests
 *
 * Tests for React Query hooks used in character creation.
 */

import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  useStartingAreas,
  useSpecies,
  useFamilies,
  useDraft,
  useCanCreateCharacter,
  useUpdateDraft,
  useCGGifts,
  characterCreationKeys,
} from '../queries';
import type { CharacterDraft } from '../types';
import { mockStartingAreas, mockSpeciesList, mockFamilies, mockDraftWithArea } from './fixtures';
import { mockCanCreateYes, mockCanCreateNo } from './mocks';

// Mock the API module
vi.mock('../api', () => ({
  getStartingAreas: vi.fn(),
  getSpecies: vi.fn(),
  getFamilies: vi.fn(),
  getDraft: vi.fn(),
  canCreateCharacter: vi.fn(),
  createDraft: vi.fn(),
  updateDraft: vi.fn(),
  deleteDraft: vi.fn(),
  submitDraftForReview: vi.fn(),
  addToRoster: vi.fn(),
  getCGExplanations: vi.fn(),
  getCGGifts: vi.fn(),
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

describe('Character Creation Query Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useStartingAreas', () => {
    it('fetches starting areas successfully', async () => {
      vi.mocked(api.getStartingAreas).mockResolvedValue(mockStartingAreas);

      const { result } = renderHook(() => useStartingAreas(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockStartingAreas);
      expect(api.getStartingAreas).toHaveBeenCalledTimes(1);
    });

    it('handles fetch error', async () => {
      vi.mocked(api.getStartingAreas).mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useStartingAreas(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).toBeDefined();
    });
  });

  describe('useSpecies', () => {
    it('fetches all species', async () => {
      vi.mocked(api.getSpecies).mockResolvedValue(mockSpeciesList);

      const { result } = renderHook(() => useSpecies(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockSpeciesList);
      expect(api.getSpecies).toHaveBeenCalledTimes(1);
    });
  });

  describe('useFamilies', () => {
    it('fetches families for given area', async () => {
      vi.mocked(api.getFamilies).mockResolvedValue(mockFamilies);

      const { result } = renderHook(() => useFamilies(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockFamilies);
      expect(api.getFamilies).toHaveBeenCalledWith(1, []);
    });

    it('does not fetch when areaId is undefined', () => {
      const { result } = renderHook(() => useFamilies(undefined), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.fetchStatus).toBe('idle');
      expect(api.getFamilies).not.toHaveBeenCalled();
    });
  });

  describe('useDraft', () => {
    it('fetches existing draft', async () => {
      vi.mocked(api.getDraft).mockResolvedValue(mockDraftWithArea);

      const { result } = renderHook(() => useDraft(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockDraftWithArea);
    });

    it('returns null when no draft exists', async () => {
      vi.mocked(api.getDraft).mockResolvedValue(null);

      const { result } = renderHook(() => useDraft(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toBeNull();
    });
  });

  describe('useCanCreateCharacter', () => {
    it('returns true when user can create', async () => {
      vi.mocked(api.canCreateCharacter).mockResolvedValue(mockCanCreateYes);

      const { result } = renderHook(() => useCanCreateCharacter(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockCanCreateYes);
      expect(result.current.data?.can_create).toBe(true);
    });

    it('returns false with reason when user cannot create', async () => {
      vi.mocked(api.canCreateCharacter).mockResolvedValue(mockCanCreateNo);

      const { result } = renderHook(() => useCanCreateCharacter(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data?.can_create).toBe(false);
      expect(result.current.data?.reason).toBe(
        'You have reached the maximum number of characters.'
      );
    });
  });

  describe('useUpdateDraft', () => {
    it('shows a picked seat before the server answers (#5130)', async () => {
      // The PATCH writes claimed_kin_slot_id and the draft reads claimed_kin_slot:
      // the optimistic merge has to carry the pick across, or the card waits for
      // the whole round trip.
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: Infinity } },
      });
      const held = { ...mockDraftWithArea, claimed_kin_slot: null, claimed_kin_pool: 4 };
      queryClient.setQueryData(characterCreationKeys.draft(), held);
      // A server that never answers: whatever the cache shows is the optimistic value.
      vi.mocked(api.updateDraft).mockReturnValue(new Promise(() => {}));
      const { result } = renderHook(() => useUpdateDraft(), {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        ),
      });

      result.current.mutate({
        draftId: held.id,
        data: { claimed_kin_slot_id: 7, claimed_kin_pool_id: null },
      });

      await waitFor(() => {
        const cached = queryClient.getQueryData<CharacterDraft>(characterCreationKeys.draft());
        expect(cached?.claimed_kin_slot).toBe(7);
        expect(cached?.claimed_kin_pool).toBeNull();
      });
    });

    it('a picked Vacancy shows at once and lets go of a hand-picked seat', async () => {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: Infinity } },
      });
      const held = { ...mockDraftWithArea, claimed_kin_slot: 7, selected_vacancy: null };
      queryClient.setQueryData(characterCreationKeys.draft(), held);
      vi.mocked(api.updateDraft).mockReturnValue(new Promise(() => {}));
      const { result } = renderHook(() => useUpdateDraft(), {
        wrapper: ({ children }: { children: ReactNode }) => (
          <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        ),
      });

      result.current.mutate({ draftId: held.id, data: { selected_vacancy_id: 12 } });

      await waitFor(() => {
        const cached = queryClient.getQueryData<CharacterDraft>(characterCreationKeys.draft());
        expect(cached?.selected_vacancy).toBe(12);
        expect(cached?.claimed_kin_slot).toBeNull();
      });
    });
  });

  describe('characterCreationKeys', () => {
    it('generates correct query keys', () => {
      expect(characterCreationKeys.all).toEqual(['character-creation']);
      expect(characterCreationKeys.startingAreas()).toEqual([
        'character-creation',
        'starting-areas',
      ]);
      expect(characterCreationKeys.species()).toEqual(['character-creation', 'species']);
      expect(characterCreationKeys.families(1)).toEqual(['character-creation', 'families', 1]);
      expect(characterCreationKeys.draft()).toEqual(['character-creation', 'draft']);
      expect(characterCreationKeys.canCreate()).toEqual(['character-creation', 'can-create']);
    });
  });

  // #5198: the gift list was cached by draft alone, so a change of path left the old
  // path's answer ("No gifts are available") on screen until a reload.
  describe('useCGGifts', () => {
    it('asks again when the path or the tradition changes, and not otherwise', async () => {
      vi.mocked(api.getCGGifts).mockResolvedValue([]);

      const { result, rerender } = renderHook(
        ({ pathId, traditionId }: { pathId: number; traditionId: number }) =>
          useCGGifts(7, pathId, traditionId),
        { wrapper: createWrapper(), initialProps: { pathId: 1, traditionId: 16 } }
      );
      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(api.getCGGifts).toHaveBeenCalledTimes(1);

      rerender({ pathId: 1, traditionId: 16 });
      expect(api.getCGGifts).toHaveBeenCalledTimes(1);

      rerender({ pathId: 2, traditionId: 16 });
      await waitFor(() => expect(api.getCGGifts).toHaveBeenCalledTimes(2));

      rerender({ pathId: 2, traditionId: 17 });
      await waitFor(() => expect(api.getCGGifts).toHaveBeenCalledTimes(3));
    });

    it('keeps the draft prefix, so invalidating a draft reaches every path and tradition', () => {
      const key = characterCreationKeys.cgGiftsFor(7, 2, 16);
      expect(key.slice(0, characterCreationKeys.cgGifts(7).length)).toEqual(
        characterCreationKeys.cgGifts(7)
      );
    });
  });
});
