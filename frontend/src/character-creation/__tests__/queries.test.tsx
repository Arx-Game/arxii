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
  characterCreationKeys,
} from '../queries';
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
  submitDraft: vi.fn(),
  addToRoster: vi.fn(),
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
    it('fetches species for given area', async () => {
      vi.mocked(api.getSpecies).mockResolvedValue(mockSpeciesList);

      const { result } = renderHook(() => useSpecies(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockSpeciesList);
      expect(api.getSpecies).toHaveBeenCalledWith(1, undefined);
    });

    it('fetches species with heritage filter', async () => {
      vi.mocked(api.getSpecies).mockResolvedValue(mockSpeciesList);

      const { result } = renderHook(() => useSpecies(1, 2), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(api.getSpecies).toHaveBeenCalledWith(1, 2);
    });

    it('does not fetch when areaId is undefined', () => {
      const { result } = renderHook(() => useSpecies(undefined), {
        wrapper: createWrapper(),
      });

      expect(result.current.isLoading).toBe(false);
      expect(result.current.fetchStatus).toBe('idle');
      expect(api.getSpecies).not.toHaveBeenCalled();
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
      expect(api.getFamilies).toHaveBeenCalledWith(1);
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

  describe('characterCreationKeys', () => {
    it('generates correct query keys', () => {
      expect(characterCreationKeys.all).toEqual(['character-creation']);
      expect(characterCreationKeys.startingAreas()).toEqual([
        'character-creation',
        'starting-areas',
      ]);
      expect(characterCreationKeys.species(1, 2)).toEqual(['character-creation', 'species', 1, 2]);
      expect(characterCreationKeys.families(1)).toEqual(['character-creation', 'families', 1]);
      expect(characterCreationKeys.draft()).toEqual(['character-creation', 'draft']);
      expect(characterCreationKeys.canCreate()).toEqual(['character-creation', 'can-create']);
    });
  });
});
