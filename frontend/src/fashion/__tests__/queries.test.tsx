/**
 * Fashion presentation/judging query + mutation hook tests (#514).
 *
 * Mocks ``apiFetch``; verifies list fetch + pagination unwrap, the present
 * mutation POST body, the judge mutation POST body, and that the API 400
 * ``detail`` message is surfaced as the thrown error.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { apiFetch } from '@/evennia_replacements/api';
import {
  useEventPresentationsQuery,
  useJudgePresentationMutation,
  usePresentOutfitMutation,
} from '../queries';

vi.mock('@/evennia_replacements/api', () => ({ apiFetch: vi.fn() }));
const mockApiFetch = vi.mocked(apiFetch);

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('useEventPresentationsQuery', () => {
  beforeEach(() => mockApiFetch.mockReset());

  it('fetches by event and unwraps the paginated results', async () => {
    const results = [{ id: 1, event: 9, presenter: 3, acclaim: 12 }];
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ count: 1, next: null, previous: null, results }),
    } as Response);

    const { result } = renderHook(() => useEventPresentationsQuery(9), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(results);
    expect(mockApiFetch).toHaveBeenCalledWith('/api/items/fashion-presentations/?event=9');
  });

  it('does not fire when the event id is undefined', () => {
    renderHook(() => useEventPresentationsQuery(undefined), { wrapper: wrapper() });
    expect(mockApiFetch).not.toHaveBeenCalled();
  });
});

describe('usePresentOutfitMutation', () => {
  beforeEach(() => mockApiFetch.mockReset());

  it('POSTs the event (and outfit when given)', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 5, event: 9, presenter: 3, acclaim: 0 }),
    } as Response);

    const { result } = renderHook(() => usePresentOutfitMutation(9), { wrapper: wrapper() });
    result.current.mutate({ event: 9, outfit: 4 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiFetch).toHaveBeenCalledWith('/api/items/fashion-presentations/', {
      method: 'POST',
      body: JSON.stringify({ event: 9, outfit: 4 }),
    });
  });

  it('surfaces the API 400 detail message', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'You already presented at this event.' }),
    } as Response);

    const { result } = renderHook(() => usePresentOutfitMutation(9), { wrapper: wrapper() });
    result.current.mutate({ event: 9 });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('You already presented at this event.');
  });
});

describe('useJudgePresentationMutation', () => {
  beforeEach(() => mockApiFetch.mockReset());

  it('POSTs the presentation id', async () => {
    mockApiFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) } as Response);

    const { result } = renderHook(() => useJudgePresentationMutation(9), { wrapper: wrapper() });
    result.current.mutate({ presentation: 7 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApiFetch).toHaveBeenCalledWith('/api/items/fashion-judgements/', {
      method: 'POST',
      body: JSON.stringify({ presentation: 7 }),
    });
  });

  it('surfaces the API 400 detail message', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'You cannot judge your own presentation.' }),
    } as Response);

    const { result } = renderHook(() => useJudgePresentationMutation(9), { wrapper: wrapper() });
    result.current.mutate({ presentation: 7 });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('You cannot judge your own presentation.');
  });
});
