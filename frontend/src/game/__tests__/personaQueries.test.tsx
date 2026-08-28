/**
 * personaQueries tests (#3412 T4 folded-in review finding) — before this,
 * `useSetActivePersonaMutation`'s errors (including an offscreen-gate refusal
 * on a CAPTURED/unconscious/DEAD/RETIRED character, #3412 slice 3) rendered
 * NOWHERE: neither `PersonaSwitcher` nor `PersonaTiles` passed a per-call
 * `onError`. This covers the hook-level `onError` toast added to fix that,
 * mirroring `useSelectCharacterMutation`'s exact pattern
 * (`frontend/src/roster/queries.ts`).
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

  it('fires an onError toast when the switch fails (e.g. an offscreen-gate refusal 4xx)', async () => {
    mockApiFetch.mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'You are captured; smuggle a message out to reach the world.' }),
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
