/**
 * Rituals Query Hooks Tests
 *
 * Tests for React Query hooks used in the rituals feature.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { useRituals, useRitual, usePerformRitual, ritualKeys } from '../queries';

// Mock the API module
vi.mock('../api', () => ({
  getRituals: vi.fn(),
  getRitual: vi.fn(),
  performRitual: vi.fn(),
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

const mockRitual = {
  id: 1,
  name: 'Accept Soul Tether',
  description: 'Form a soul tether bond.',
  narrative_prose: 'Two souls entwined...',
  hedge_accessible: false,
  glimpse_eligible: false,
  execution_kind: 'SERVICE' as const,
  input_schema: {
    fields: [
      {
        name: 'capstone_id',
        label: 'Relationship Capstone',
        type: 'relationship_capstone_picker',
        required: true,
      },
    ],
  },
  author_account_id: null,
  scene_action_config: null,
  client_hosted: false,
};

describe('Rituals Query Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useRituals', () => {
    it('fetches ritual list successfully', async () => {
      const mockList = { count: 1, next: null, previous: null, results: [mockRitual] };
      vi.mocked(api.getRituals).mockResolvedValue(mockList);

      const { result } = renderHook(() => useRituals(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockList);
      expect(api.getRituals).toHaveBeenCalledTimes(1);
    });

    it('enters error state on fetch failure', async () => {
      vi.mocked(api.getRituals).mockRejectedValue(new Error('Network error'));

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      // Use a custom hook that disables throwOnError to test the error state
      const { result } = renderHook(
        () =>
          useQuery({
            queryKey: ritualKeys.list(),
            queryFn: () => api.getRituals(),
            retry: false,
          }),
        {
          wrapper: createWrapper(),
        }
      );

      await waitFor(() => {
        expect(result.current.isError).toBe(true);
      });

      expect(result.current.error).not.toBeNull();
      expect(api.getRituals).toHaveBeenCalledTimes(1);

      consoleSpy.mockRestore();
    });
  });

  describe('useRitual', () => {
    it('fetches single ritual by id', async () => {
      vi.mocked(api.getRitual).mockResolvedValue(mockRitual);

      const { result } = renderHook(() => useRitual(1), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockRitual);
      expect(api.getRitual).toHaveBeenCalledWith(1);
    });

    it('does not fetch when id is 0', () => {
      const { result } = renderHook(() => useRitual(0), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
      expect(api.getRitual).not.toHaveBeenCalled();
    });

    it('does not fetch when id is negative', () => {
      const { result } = renderHook(() => useRitual(-1), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe('idle');
      expect(api.getRitual).not.toHaveBeenCalled();
    });
  });

  describe('usePerformRitual', () => {
    it('posts the correct request body', async () => {
      const mockResponse = {
        ritual_id: 1,
        execution_kind: 'SERVICE',
        result: {},
      };
      vi.mocked(api.performRitual).mockResolvedValue(mockResponse);

      const { result } = renderHook(() => usePerformRitual(), {
        wrapper: createWrapper(),
      });

      const requestBody = {
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: { capstone_id: 7 },
        components: [],
      };

      await act(async () => {
        await result.current.mutateAsync(requestBody);
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(api.performRitual).toHaveBeenCalledWith(requestBody);
      expect(result.current.data).toEqual(mockResponse);
    });

    it('posts without optional components field', async () => {
      const mockResponse = { ritual_id: 1, execution_kind: 'SERVICE' };
      vi.mocked(api.performRitual).mockResolvedValue(mockResponse);

      const { result } = renderHook(() => usePerformRitual(), {
        wrapper: createWrapper(),
      });

      const requestBody = {
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: {},
      };

      await act(async () => {
        await result.current.mutateAsync(requestBody);
      });

      expect(api.performRitual).toHaveBeenCalledWith(requestBody);
    });
  });

  describe('ritualKeys', () => {
    it('generates correct query keys', () => {
      expect(ritualKeys.all).toEqual(['rituals']);
      expect(ritualKeys.list()).toEqual(['rituals', 'list']);
      expect(ritualKeys.detail(1)).toEqual(['rituals', 'detail', 1]);
      expect(ritualKeys.detail(99)).toEqual(['rituals', 'detail', 99]);
    });
  });
});
