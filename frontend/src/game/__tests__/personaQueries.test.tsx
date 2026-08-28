/**
 * personaQueries tests (#3412 T4 folded-in review finding + T5 close-out) —
 * before T4, `useSetActivePersonaMutation`'s errors (including an
 * offscreen-gate refusal on a CAPTURED/unconscious/DEAD/RETIRED character,
 * #3412 slice 3) rendered NOWHERE: neither `PersonaSwitcher` nor
 * `PersonaTiles` passed a per-call `onError`. T4 added the hook-level
 * `onError` toast, mirroring `useSelectCharacterMutation`'s exact pattern
 * (`frontend/src/roster/queries.ts`) — but the fetcher itself still threw a
 * fixed generic message regardless of the response body, so the toast never
 * showed the actual gate reason. T5 fixed the fetcher to surface the
 * response's `{"detail"}` via `readErrorDetail` (`@/lib/errors`) when
 * present, falling back to the generic copy otherwise — covered below.
 */
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { useSetActivePersonaMutation } from '../personaQueries';

const mockApiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { toast } from 'sonner';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useSetActivePersonaMutation', () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it('fires an onError toast carrying the gate reason (e.g. an offscreen-gate refusal 4xx)', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'You are captured; smuggle a message out to reach the world.' }),
    });

    const { result } = renderHook(() => useSetActivePersonaMutation(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate(7);
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(toast.error).toHaveBeenCalledWith(
      'You are captured; smuggle a message out to reach the world.'
    );
  });

  it('falls back to the generic message when the response has no {detail}', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({}),
    });

    const { result } = renderHook(() => useSetActivePersonaMutation(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate(7);
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(toast.error).toHaveBeenCalledWith('Could not switch to that identity.');
  });

  it('does not toast on a successful switch', async () => {
    mockApiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ active_persona_id: 7 }),
    });

    const { result } = renderHook(() => useSetActivePersonaMutation(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate(7);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(toast.error).not.toHaveBeenCalled();
  });
});
