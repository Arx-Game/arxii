/**
 * useStoryBuilderAction dispatch-result handling (#2450), mirroring
 * `world-builder/queries.test.tsx` (#2449 fix pass).
 *
 * The dispatch endpoint returns HTTP 200 with `{success: false, message}` for
 * a business-rule refusal (see `DispatchResultSerializer`,
 * `src/actions/serializers.py:270-275`) — a rejection is NOT an HTTP error.
 * Verifies the mutation reads `success` and toasts an error + skips every
 * cache invalidation on a refusal, instead of treating the 200 as a success —
 * plus the temp-room-instances cache invalidation this app adds on top of
 * world-builder's area-manager/area-list invalidation.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import { apiFetch } from '@/evennia_replacements/api';
import { storyBuilderKeys, useStoryBuilderAction } from './queries';

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

describe('useStoryBuilderAction', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    vi.mocked(toast.error).mockReset();
    vi.mocked(toast.success).mockReset();
  });

  it('toasts an error and skips invalidation on a success:false dispatch', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: false, message: 'Area already has a room there.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryBuilderAction(7, 3), { wrapper: Wrapper });
    result.current.mutate({ key: 'story_dig_room', kwargs: { area_id: 3, name: 'Foo' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('Area already has a room there.');
    expect(toast.success).not.toHaveBeenCalled();
    expect(qc.invalidateQueries).not.toHaveBeenCalled();
  });

  it('toasts success and invalidates the manager on a success:true dispatch', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, message: 'Room dug.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryBuilderAction(7, 3), { wrapper: Wrapper });
    result.current.mutate({ key: 'story_dig_room', kwargs: { area_id: 3, name: 'Foo' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.success).toHaveBeenCalledWith('Room dug.');
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: storyBuilderKeys.manager(3) });
  });

  it('invalidates the areas list/detail on a create_story_area success', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, message: 'Area created.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryBuilderAction(7, null), { wrapper: Wrapper });
    result.current.mutate({ key: 'create_story_area', kwargs: { name: 'Hideout' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(qc.invalidateQueries).toHaveBeenCalledWith({
      queryKey: [...storyBuilderKeys.all, 'areas'],
    });
    expect(qc.invalidateQueries).toHaveBeenCalledWith({
      queryKey: [...storyBuilderKeys.all, 'area'],
    });
  });

  it('invalidates the instances list on a spin_up_scene_room success', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, message: 'Scene room spun up.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryBuilderAction(7, null), { wrapper: Wrapper });
    result.current.mutate({ key: 'spin_up_scene_room', kwargs: { name: 'Alley' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(qc.invalidateQueries).toHaveBeenCalledWith({
      queryKey: storyBuilderKeys.instances(),
    });
  });

  it('toasts a network/HTTP error from the dispatch call', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'That story area isn’t yours.' }),
    } as Response);
    const { Wrapper } = wrapper();

    const { result } = renderHook(() => useStoryBuilderAction(7, 3), { wrapper: Wrapper });
    result.current.mutate({ key: 'story_remove_room', kwargs: { room_id: 9 } });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('That story area isn’t yours.');
  });
});
