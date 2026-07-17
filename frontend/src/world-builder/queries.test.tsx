/**
 * useWorldBuilderAction dispatch-result handling (#2449 fix pass).
 *
 * The dispatch endpoint returns HTTP 200 with `{success: false, message}` for
 * a business-rule refusal (see `DispatchResultSerializer`,
 * `src/actions/serializers.py:270-275`) — a rejection is NOT an HTTP error.
 * Verifies the mutation reads `success` and toasts an error + skips every
 * cache invalidation on a refusal, instead of treating the 200 as a success.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import { apiFetch } from '@/evennia_replacements/api';
import { useWorldBuilderAction } from './queries';

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

describe('useWorldBuilderAction', () => {
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

    const { result } = renderHook(() => useWorldBuilderAction(7, 3), { wrapper: Wrapper });
    result.current.mutate({ key: 'staff_dig_room', kwargs: { area_id: 3, name: 'Foo' } });
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

    const { result } = renderHook(() => useWorldBuilderAction(7, 3), { wrapper: Wrapper });
    result.current.mutate({ key: 'staff_dig_room', kwargs: { area_id: 3, name: 'Foo' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.success).toHaveBeenCalledWith('Room dug.');
    expect(qc.invalidateQueries).toHaveBeenCalled();
  });
});
