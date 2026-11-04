/**
 * useWorldBuilderAction (#4988): a seat move refreshes the region map like a carve does.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import { useWorldBuilderAction } from '../queries';

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  dispatchWorldBuilder: vi.fn().mockResolvedValue({ message: 'moved', success: true, data: {} }),
}));

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

test('atlas_move_seat invalidates the region map pips so the seat dot moves', async () => {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useWorldBuilderAction(7, null), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({
      key: 'atlas_move_seat',
      kwargs: { area_id: 9, pip: [3, 13] },
    });
  });
  const keys = invalidate.mock.calls.map((call) => JSON.stringify(call[0]?.queryKey));
  expect(keys).toContain(JSON.stringify(['world-builder', 'region-map-pips']));
});
