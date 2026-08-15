/**
 * Voyage mutation hooks' dispatch-result handling (review fix, #3155).
 *
 * `dispatchVoyageAction` resolves through `postDispatchAction`
 * (`combat/api.ts`), which returns HTTP 200 with `{success: false, message}`
 * for a business-rule refusal (e.g. "no route to that hub") — a rejection is
 * NOT an HTTP error. Mirrors `story-rooms/queries.test.tsx`: verifies each
 * hook reads `success` and toasts an error + skips invalidation on a
 * refusal, instead of treating the 200 as a success.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import { apiFetch } from '@/evennia_replacements/api';
import { TRAVEL_KEYS, useStartVoyage, useRespondVoyageInvite, useAbandonVoyage } from './queries';

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

describe('travel mutation hooks', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    vi.mocked(toast.error).mockReset();
    vi.mocked(toast.success).mockReset();
  });

  it('useStartVoyage toasts an error and skips invalidation on a success:false dispatch', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: false, message: 'No route to that hub.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStartVoyage(7), { wrapper: Wrapper });
    result.current.mutate({ destination_id: 3, travel_method_id: 1 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('No route to that hub.');
    expect(toast.success).not.toHaveBeenCalled();
    expect(qc.invalidateQueries).not.toHaveBeenCalled();
  });

  it('useStartVoyage toasts success and invalidates voyages on a success:true dispatch', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, message: 'Voyage started.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useStartVoyage(7), { wrapper: Wrapper });
    result.current.mutate({ destination_id: 3, travel_method_id: 1 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.success).toHaveBeenCalledWith('Voyage started.');
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: TRAVEL_KEYS.voyages });
  });

  it('useStartVoyage toasts the error message on a hard HTTP failure', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'Not your character.' }),
    } as Response);
    const { Wrapper } = wrapper();

    const { result } = renderHook(() => useStartVoyage(7), { wrapper: Wrapper });
    result.current.mutate({ destination_id: 3, travel_method_id: 1 });
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('Not your character.');
  });

  it('useRespondVoyageInvite toasts an error and skips invalidation on a claimed-slot refusal', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          success: false,
          message: 'Someone else already claimed the leader slot.',
        }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useRespondVoyageInvite(7), { wrapper: Wrapper });
    result.current.mutate({ invite_id: 5, accept: true });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('Someone else already claimed the leader slot.');
    expect(qc.invalidateQueries).not.toHaveBeenCalled();
  });

  it('useRespondVoyageInvite invalidates both invites and voyages on acceptance', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: true, message: 'Invitation accepted.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useRespondVoyageInvite(7), { wrapper: Wrapper });
    result.current.mutate({ invite_id: 5, accept: true });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: TRAVEL_KEYS.invites });
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: TRAVEL_KEYS.voyages });
  });

  it('useAbandonVoyage toasts an error and skips invalidation when already in transit', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ success: false, message: 'Cannot abandon mid-leg.' }),
    } as Response);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useAbandonVoyage(7), { wrapper: Wrapper });
    result.current.mutate();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('Cannot abandon mid-leg.');
    expect(qc.invalidateQueries).not.toHaveBeenCalled();
  });
});
