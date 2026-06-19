import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import * as api from '../../api';
import { useUseItem } from '../useUseItem';

vi.mock('../../api');

function createWrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('useUseItem', () => {
  it('invalidates the inventory query for the character on success', async () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    vi.mocked(api.postUseItem).mockResolvedValue({
      charges_remaining: 1,
      destroyed: false,
      soft_deleted: false,
      applied_effect_count: 1,
    });
    const { result } = renderHook(() => useUseItem(42), { wrapper: createWrapper(qc) });
    await act(async () => {
      await result.current.mutateAsync(7);
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.postUseItem).toHaveBeenCalledWith(7);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['inventory', 42] });
  });
});
