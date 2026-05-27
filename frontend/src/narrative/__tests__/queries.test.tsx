/**
 * Narrative Query Hooks Tests
 *
 * Tests for React Query hooks used in the narrative feature.
 */

import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { configureStore } from '@reduxjs/toolkit';
import { Provider } from 'react-redux';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import {
  useMyMessages,
  useAcknowledgeDelivery,
  useUnreadNarrativeCount,
  narrativeKeys,
} from '../queries';
import { authSlice } from '@/store/authSlice';

// Mock the API module
vi.mock('../api', () => ({
  getMyMessages: vi.fn(),
  acknowledgeDelivery: vi.fn(),
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
  // `useMyMessages` reads `s.auth.account` to gate on the user being
  // logged in (the badge that consumes it renders unconditionally in the
  // header, so without this guard it 403s on the login page and trips
  // the error boundary). Tests must provide a populated store or the
  // hook stays disabled and never fetches.
  const store = configureStore({
    reducer: { auth: authSlice.reducer },
    preloadedState: {
      auth: {
        account: {
          id: 1,
          username: 'test',
          display_name: 'test',
          last_login: null,
          email: 'test@example.com',
          email_verified: true,
          can_create_characters: false,
          is_staff: false,
          available_characters: [],
          pending_applications: [],
        },
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <Provider store={store}>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </Provider>
    );
  };
}

const mockDelivery = {
  id: 1,
  message: {
    id: 10,
    body: 'The winds of change blow across the realm.',
    category: 'story' as const,
    sender_account: null,
    related_story: 5,
    related_beat_completion: null,
    related_episode_resolution: null,
    sent_at: '2026-04-19T10:00:00Z',
  },
  delivered_at: '2026-04-19T10:01:00Z',
  acknowledged_at: null,
};

describe('Narrative Query Hooks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useMyMessages', () => {
    it('fetches paginated deliveries successfully', async () => {
      const mockData = {
        count: 1,
        next: null,
        previous: null,
        results: [mockDelivery],
      };
      vi.mocked(api.getMyMessages).mockResolvedValue(mockData);

      const { result } = renderHook(() => useMyMessages(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(result.current.data).toEqual(mockData);
      expect(api.getMyMessages).toHaveBeenCalledWith(undefined);
    });

    it('passes category filter to API', async () => {
      const mockData = { count: 0, next: null, previous: null, results: [] };
      vi.mocked(api.getMyMessages).mockResolvedValue(mockData);

      const { result } = renderHook(() => useMyMessages({ category: 'story' }), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(api.getMyMessages).toHaveBeenCalledWith({ category: 'story' });
    });

    it('passes acknowledged filter to API', async () => {
      const mockData = { count: 3, next: null, previous: null, results: [] };
      vi.mocked(api.getMyMessages).mockResolvedValue(mockData);

      const { result } = renderHook(() => useMyMessages({ acknowledged: false }), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current.isSuccess).toBe(true);
      });

      expect(api.getMyMessages).toHaveBeenCalledWith({ acknowledged: false });
    });

    it('enters error state on fetch failure', async () => {
      vi.mocked(api.getMyMessages).mockRejectedValue(new Error('Network error'));

      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      const { result } = renderHook(() => useMyMessages(), {
        wrapper: createWrapper(),
      });

      await waitFor(
        () => {
          return !result.current.isLoading || result.current.error !== null;
        },
        { timeout: 2000 }
      );

      expect(api.getMyMessages).toHaveBeenCalledTimes(1);

      consoleSpy.mockRestore();
    });
  });

  describe('useAcknowledgeDelivery', () => {
    it('calls acknowledgeDelivery and invalidates narrative cache', async () => {
      const updatedDelivery = { ...mockDelivery, acknowledged_at: '2026-04-19T10:05:00Z' };
      vi.mocked(api.acknowledgeDelivery).mockResolvedValue(updatedDelivery);

      // Prime the cache so we can verify invalidation
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
      });
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

      const wrapper = ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      );

      const { result } = renderHook(() => useAcknowledgeDelivery(), { wrapper });

      await act(async () => {
        await result.current.mutateAsync(1);
      });

      expect(api.acknowledgeDelivery).toHaveBeenCalledWith(1);
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: narrativeKeys.all })
      );
    });
  });

  describe('useUnreadNarrativeCount', () => {
    it('returns count of unacknowledged messages', async () => {
      const mockData = { count: 5, next: null, previous: null, results: [] };
      vi.mocked(api.getMyMessages).mockResolvedValue(mockData);

      const { result } = renderHook(() => useUnreadNarrativeCount(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => {
        expect(result.current).toBe(5);
      });

      expect(api.getMyMessages).toHaveBeenCalledWith({ acknowledged: false });
    });

    it('returns 0 when data is not yet loaded', () => {
      vi.mocked(api.getMyMessages).mockImplementation(() => new Promise(() => {}));

      const { result } = renderHook(() => useUnreadNarrativeCount(), {
        wrapper: createWrapper(),
      });

      expect(result.current).toBe(0);
    });
  });

  describe('narrativeKeys', () => {
    it('generates correct query keys', () => {
      expect(narrativeKeys.all).toEqual(['narrative']);
      expect(narrativeKeys.myMessages()).toEqual(['narrative', 'my-messages', undefined]);
      expect(narrativeKeys.myMessages({ category: 'story' })).toEqual([
        'narrative',
        'my-messages',
        { category: 'story' },
      ]);
      expect(narrativeKeys.myMessages({ acknowledged: false })).toEqual([
        'narrative',
        'my-messages',
        { acknowledged: false },
      ]);
    });
  });
});
