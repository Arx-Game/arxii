/**
 * usePurchaseUnlockMutation cache invalidation (#4090 final-review Minor fix).
 *
 * A language breakthrough raises the trait rating the character sheet's
 * Languages section reads (`species.queries.useMyLanguages`), so the purchase
 * mutation must also invalidate `speciesKeys.myLanguages()` on success — but
 * only for `unlock_type: 'language_breakthrough'`, never for the other unlock
 * kinds (class_level, thread_xp_lock, skill_breakthrough), which don't touch
 * a language rating.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { purchaseProgressionUnlock } from './api';
import { usePurchaseUnlockMutation } from './queries';
import { speciesKeys } from '@/species/queries';
import type { PurchaseUnlockResponse } from './types';

vi.mock('./api', () => ({
  purchaseProgressionUnlock: vi.fn(),
}));

const mockPurchase = vi.mocked(purchaseProgressionUnlock);

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, Wrapper };
}

describe('usePurchaseUnlockMutation', () => {
  beforeEach(() => {
    mockPurchase.mockReset();
  });

  it('invalidates myLanguages on a language breakthrough purchase', async () => {
    mockPurchase.mockResolvedValue({
      unlock_type: 'language_breakthrough',
      language_id: 4,
    } as PurchaseUnlockResponse);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => usePurchaseUnlockMutation(), { wrapper: Wrapper });
    result.current.mutate({ unlock_type: 'language_breakthrough', language_id: 4 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(qc.invalidateQueries).toHaveBeenCalledWith({ queryKey: speciesKeys.myLanguages() });
  });

  it('does not invalidate myLanguages on a skill breakthrough purchase', async () => {
    mockPurchase.mockResolvedValue({
      unlock_type: 'skill_breakthrough',
      skill_id: 5,
    } as PurchaseUnlockResponse);
    const { qc, Wrapper } = wrapper();

    const { result } = renderHook(() => usePurchaseUnlockMutation(), { wrapper: Wrapper });
    result.current.mutate({ unlock_type: 'skill_breakthrough', skill_id: 5 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(qc.invalidateQueries).not.toHaveBeenCalledWith({
      queryKey: speciesKeys.myLanguages(),
    });
  });
});
