import { act, renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';

import { useReorderSubscriptions } from '../queries';
import { updateSubscription } from '../api';
import type { ChannelSubscription } from '../types';

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  updateSubscription: vi.fn(),
}));
vi.mock('@/store/hooks', () => ({
  useAccount: () => null,
  useAppSelector: () => false,
}));

describe('reordering subscriptions', () => {
  it('patches only moved rows and waits for every patch', async () => {
    let finish!: () => void;
    const delayed = new Promise<void>((resolve) => {
      finish = resolve;
    });
    vi.mocked(updateSubscription).mockReset();
    vi.mocked(updateSubscription).mockImplementation(async (id) => {
      if (id === 3) await delayed;
      return {} as ChannelSubscription;
    });
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useReorderSubscriptions(), { wrapper });
    const rows = [
      { id: 1, sort_order: 0 },
      { id: 2, sort_order: 2 },
      { id: 3, sort_order: 1 },
    ] as ChannelSubscription[];
    let completed = false;
    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.mutateAsync(rows).then(() => {
        completed = true;
      });
      await vi.waitFor(() => expect(updateSubscription).toHaveBeenCalledTimes(2));
      expect(updateSubscription).toHaveBeenCalledWith(2, { sort_order: 1 });
      expect(updateSubscription).toHaveBeenCalledWith(3, { sort_order: 2 });
      expect(completed).toBe(false);
      finish();
      await pending;
    });
    expect(completed).toBe(true);
  });
});
