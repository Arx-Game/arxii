/**
 * Tests for the #3412 durable character-selection wire: `postSelectEntry`
 * (api.ts) and `useSelectCharacterMutation` (queries.ts).
 */
import type { ReactNode } from 'react';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { apiFetch } from '@/evennia_replacements/api';
import { toast } from 'sonner';
import { postSelectEntry } from '../api';
import { useSelectCharacterMutation } from '../queries';
import type { SelectedEntryResult } from '../types';

function mockOkResponse(data: unknown) {
  return { ok: true, json: () => Promise.resolve(data) } as Response;
}

function mockErrorResponse() {
  return { ok: false } as Response;
}

describe('postSelectEntry', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('POSTs {entry_id} to /api/roster/entries/select/ and returns the fragment', async () => {
    const data: SelectedEntryResult = {
      selected_entry_id: 7,
      selected_entry: {
        id: 7,
        name: 'Aria',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 1,
        active_persona_id: 1,
      },
    };
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

    const result = await postSelectEntry(7);

    expect(apiFetch).toHaveBeenCalledWith('/api/roster/entries/select/', {
      method: 'POST',
      body: JSON.stringify({ entry_id: 7 }),
    });
    expect(result).toEqual(data);
  });

  it('sends entry_id: null to clear the selection', async () => {
    const data: SelectedEntryResult = { selected_entry_id: null, selected_entry: null };
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

    const result = await postSelectEntry(null);

    expect(apiFetch).toHaveBeenCalledWith('/api/roster/entries/select/', {
      method: 'POST',
      body: JSON.stringify({ entry_id: null }),
    });
    expect(result).toEqual(data);
  });

  it('throws on an error response (e.g. a foreign entry id)', async () => {
    vi.mocked(apiFetch).mockResolvedValue(mockErrorResponse());

    await expect(postSelectEntry(999)).rejects.toThrow('Could not switch to that character.');
  });
});

describe('useSelectCharacterMutation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function createWrapperWithClient() {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    function Wrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    }
    return { wrapper: Wrapper, client };
  }

  it('passes the entry id through to postSelectEntry', async () => {
    const data: SelectedEntryResult = {
      selected_entry_id: 7,
      selected_entry: {
        id: 7,
        name: 'Aria',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 1,
        active_persona_id: 1,
      },
    };
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

    const { wrapper } = createWrapperWithClient();
    const { result } = renderHook(() => useSelectCharacterMutation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(7);
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiFetch).toHaveBeenCalledWith('/api/roster/entries/select/', {
      method: 'POST',
      body: JSON.stringify({ entry_id: 7 }),
    });
  });

  it('invalidates the ["account"] query on success — useAccountQuery re-hydrates from there', async () => {
    const data: SelectedEntryResult = { selected_entry_id: null, selected_entry: null };
    vi.mocked(apiFetch).mockResolvedValue(mockOkResponse(data));

    const { wrapper, client } = createWrapperWithClient();
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');
    const { result } = renderHook(() => useSelectCharacterMutation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(null);
    });

    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['account'] });
    });
  });

  // #3412 review fix (finding 1): a failed select POST must surface, not be
  // swallowed silently — matches useSendRosterApplication's onError pattern.
  it('surfaces a failed select via toast.error instead of swallowing it', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ok: false } as Response);

    const { wrapper } = createWrapperWithClient();
    const { result } = renderHook(() => useSelectCharacterMutation(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync(999).catch(() => {});
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    // postSelectEntry throws a real Error, so onError surfaces its message
    // (not the generic fallback, which only covers a non-Error rejection).
    expect(toast.error).toHaveBeenCalledWith('Could not switch to that character.');
  });
});
