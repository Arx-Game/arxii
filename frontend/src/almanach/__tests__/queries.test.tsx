/**
 * Almanach de Catenys frontend queries (#3983 Task 7).
 *
 * `useLadder` is the TDD anchor from the task brief. `useAlmanachMutation` gets
 * its own coverage of the dispatch-result contract it shares with
 * `useWorldBuilderAction` (`world-builder/queries.test.tsx`): a `success: false`
 * dispatch is a business-rule refusal (HTTP 200), not an error, so it must
 * toast and skip cache invalidation instead of being treated as a landed action.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { toast } from 'sonner';

import * as api from '../api';
import { useAlmanachMutation, useLadder } from '../queries';

vi.mock('../api');
vi.mock('@/world-builder/useWorldBuilderActor', () => ({
  useWorldBuilderActor: () => 7,
}));
vi.mock('sonner', () => ({
  toast: Object.assign(vi.fn(), { error: vi.fn(), success: vi.fn() }),
}));

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, Wrapper };
}

describe('useLadder', () => {
  beforeEach(() => {
    vi.mocked(api.fetchLadder).mockReset();
  });

  it('fetches the staff ladder for a realm', async () => {
    vi.mocked(api.fetchLadder).mockResolvedValue({
      rows: [
        {
          title_id: 1,
          name: 'Fervor',
          is_defined: true,
          tier: 'duchy',
          level: 56,
          parent_title_id: null,
          house_id: null,
          house_name: '',
          state: 'Unclaimed',
          is_seat_of: '',
          sworn_to: 'Piropa (crown)',
          demesne: 1,
          vassals: 2,
          claimable: true,
          seat_domain_id: null,
          comes_with: '',
          chain_top_id: 1,
          claimant_name: '',
        },
      ],
      unclaimed_by_tier: { duchy: 1, county: 2, barony: 4 },
    });
    const { Wrapper } = wrapper();

    const { result } = renderHook(() => useLadder(7, 'staff'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.data?.rows[0].name).toBe('Fervor'));
    expect(api.fetchLadder).toHaveBeenCalledWith(7, 'staff');
  });
});

describe('useAlmanachMutation', () => {
  beforeEach(() => {
    vi.mocked(api.dispatchAlmanach).mockReset();
    vi.mocked(toast.error).mockReset();
    vi.mocked(toast.success).mockReset();
  });

  it('toasts an error and skips invalidation on a success:false dispatch', async () => {
    vi.mocked(api.dispatchAlmanach).mockResolvedValue({
      success: false,
      message: 'That rung is already held.',
    });
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useAlmanachMutation('almanach_plant_rung'), {
      wrapper: Wrapper,
    });
    result.current.mutate({ realm_id: 7, tier: 'county', name: 'Test' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.error).toHaveBeenCalledWith('That rung is already held.');
    expect(toast.success).not.toHaveBeenCalled();
    expect(qc.invalidateQueries).not.toHaveBeenCalled();
    expect(api.dispatchAlmanach).toHaveBeenCalledWith(7, 'almanach_plant_rung', {
      realm_id: 7,
      tier: 'county',
      name: 'Test',
    });
  });

  it('toasts success and invalidates every cached almanach read on success', async () => {
    vi.mocked(api.dispatchAlmanach).mockResolvedValue({
      success: true,
      message: 'Rung planted.',
    });
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => useAlmanachMutation('almanach_plant_rung'), {
      wrapper: Wrapper,
    });
    result.current.mutate({ realm_id: 7, tier: 'county', name: 'Test' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(toast.success).toHaveBeenCalledWith('Rung planted.');
    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: ['almanach'] });
  });
});
