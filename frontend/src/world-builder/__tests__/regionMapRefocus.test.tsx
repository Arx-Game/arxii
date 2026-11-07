/**
 * #4993: a map open in one tab redraws when staff return from carving in another, even
 * inside the query's staleTime.
 */
import { QueryClient, QueryClientProvider, focusManager } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

import { fetchRegionMapPips } from '../api';
import { useRegionMapPipsQuery } from '../queries';

vi.mock('../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api')>()),
  fetchRegionMapPips: vi.fn().mockResolvedValue({ region: { id: 1 } }),
}));

test('returning to the tab refetches the pips while they are still fresh', async () => {
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const { result } = renderHook(() => useRegionMapPipsQuery(1), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(fetchRegionMapPips).toHaveBeenCalledTimes(1);

  act(() => {
    focusManager.setFocused(false);
    focusManager.setFocused(true);
  });
  await waitFor(() => expect(fetchRegionMapPips).toHaveBeenCalledTimes(2));
  focusManager.setFocused(undefined);
});
