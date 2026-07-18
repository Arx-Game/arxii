/**
 * useStoryRoomAction dispatch-result handling (#2450 Fix 2), mirroring
 * `story-builder/queries.test.tsx`.
 *
 * The dispatch endpoint returns HTTP 200 with `{success: false, message}` for
 * a business-rule refusal (see `DispatchResultSerializer`,
 * `src/actions/serializers.py:270-275`) — a rejection is NOT an HTTP error.
 * Verifies the mutation reads `success` and toasts an error + skips the
 * grants-list invalidation on a refusal, instead of treating the 200 as a
 * success.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import { apiFetch } from '@/evennia_replacements/api';
import { storyRoomsKeys, useStoryRoomAction } from './queries';

vi.mock('@/evennia_replacements/api', () => ({ apiFetch: vi.fn() }));
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

const mockApiFetch = vi.mocked(apiFetch);

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, Wrapper };
}

describe('useStoryRoomAction', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    vi.mocked(toast.error).mockReset();
    vi.mocked(toast.success).mockReset();
  });

  it('toasts an error and skips invalidation on a success:false dispatch', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({ success: false, message: 'You have no invitation to that room.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryRoomAction(), { wrapper: Wrapper });
    result.current.mutate({ characterId: 7, key: 'join_story_room', kwargs: { room_id: 3 } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('You have no invitation to that room.');
    expect(toast.success).not.toHaveBeenCalled();
    expect(qc.invalidateQueries).not.toHaveBeenCalled();
  });

  it('toasts success and invalidates the grants list on a success:true join', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, message: 'You join The Dungeon.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryRoomAction(), { wrapper: Wrapper });
    result.current.mutate({ characterId: 7, key: 'join_story_room', kwargs: { room_id: 3 } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.success).toHaveBeenCalledWith('You join The Dungeon.');
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: storyRoomsKeys.myGrants() });
  });

  it('toasts success and invalidates the grants list on a success:true leave', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, message: 'You leave.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryRoomAction(), { wrapper: Wrapper });
    result.current.mutate({ characterId: 7, key: 'leave_story_room', kwargs: {} });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.success).toHaveBeenCalledWith('You leave.');
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: storyRoomsKeys.myGrants() });
  });

  it('toasts the error message on a hard HTTP failure', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'Not your character.' }),
    } as Response);
    const { Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryRoomAction(), { wrapper: Wrapper });
    result.current.mutate({ characterId: 7, key: 'join_story_room', kwargs: { room_id: 3 } });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('Not your character.');
  });
});
