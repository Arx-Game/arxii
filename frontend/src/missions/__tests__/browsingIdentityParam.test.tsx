/**
 * #3479 Task 5: the player-scoped mission hooks send the tab's browsing
 * identity as an `entry_id` QUERY PARAM (the backend advertises it on every
 * MissionJournalViewSet / MissionBoardViewSet operation, POSTs included).
 *
 * Mocks the transport (apiFetch) and `useBrowsingIdentity`, exercising the
 * REAL api module through the REAL hooks so the assertion covers the full
 * hook-to-URL path. With no browsing identity (entryId null) the param is
 * omitted entirely, never sent as an empty string (missions 400s on "").
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

const apiFetch = vi.fn();
vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

const useBrowsingIdentity = vi.fn();
vi.mock('@/roster/useBrowsingIdentity', () => ({
  useBrowsingIdentity: () => useBrowsingIdentity(),
}));

import {
  useBeat,
  useBoardPostings,
  useGroupBeat,
  useJournal,
  useOpportunities,
  usePendingInvites,
  useResolveBeat,
  useTakeBoardPosting,
} from '../queries';

function jsonResponse(body: unknown) {
  return { ok: true, status: 200, json: () => Promise.resolve(body) };
}

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

function identity(entryId: number | null) {
  useBrowsingIdentity.mockReturnValue({ entryId, name: null, entry: null });
}

function calledUrls(): string[] {
  return apiFetch.mock.calls.map((call) => String(call[0]));
}

beforeEach(() => {
  apiFetch.mockReset();
  useBrowsingIdentity.mockReset();
});

describe('player mission reads carry entry_id (#3479)', () => {
  it('useJournal appends ?entry_id when the tab has a browsing identity', async () => {
    identity(5);
    apiFetch.mockResolvedValue(jsonResponse({ next: null, results: [] }));
    renderHook(() => useJournal(), { wrapper: wrapper() });
    await waitFor(() => expect(calledUrls()).toContain('/api/missions/journal/?entry_id=5'));
  });

  it('useJournal omits the param entirely when entryId is null', async () => {
    identity(null);
    apiFetch.mockResolvedValue(jsonResponse({ next: null, results: [] }));
    renderHook(() => useJournal(), { wrapper: wrapper() });
    await waitFor(() => expect(calledUrls()).toContain('/api/missions/journal/'));
    expect(calledUrls().some((u) => u.includes('entry_id'))).toBe(false);
  });

  it('usePendingInvites appends ?entry_id', async () => {
    identity(5);
    apiFetch.mockResolvedValue(jsonResponse([]));
    renderHook(() => usePendingInvites(), { wrapper: wrapper() });
    await waitFor(() =>
      expect(calledUrls()).toContain('/api/missions/journal/pending-invites/?entry_id=5')
    );
  });

  it('useOpportunities appends ?entry_id', async () => {
    identity(5);
    apiFetch.mockResolvedValue(jsonResponse({ here: [], nearby: [], your_organizations: [] }));
    renderHook(() => useOpportunities(), { wrapper: wrapper() });
    await waitFor(() =>
      expect(calledUrls()).toContain('/api/missions/journal/opportunities/?entry_id=5')
    );
  });

  it('useBeat appends ?entry_id', async () => {
    identity(5);
    apiFetch.mockResolvedValue(jsonResponse(null));
    renderHook(() => useBeat(7, 'room'), { wrapper: wrapper() });
    await waitFor(() => expect(calledUrls()).toContain('/api/missions/journal/7/beat/?entry_id=5'));
  });

  it('useGroupBeat appends ?entry_id', async () => {
    identity(5);
    apiFetch.mockResolvedValue(jsonResponse({ group_beat: null, resolved: null }));
    renderHook(() => useGroupBeat(7, 'room'), { wrapper: wrapper() });
    await waitFor(() =>
      expect(calledUrls()).toContain('/api/missions/journal/7/group-beat/?entry_id=5')
    );
  });

  it('useBoardPostings appends ?entry_id', async () => {
    identity(5);
    apiFetch.mockResolvedValue(jsonResponse({ count: 0, results: [] }));
    renderHook(() => useBoardPostings(31), { wrapper: wrapper() });
    await waitFor(() =>
      expect(calledUrls()).toContain('/api/missions/boards/31/postings/?entry_id=5')
    );
  });
});

describe('player mission mutations carry entry_id (#3479)', () => {
  it('useResolveBeat POSTs to a ?entry_id URL', async () => {
    identity(5);
    apiFetch.mockResolvedValue(
      jsonResponse({
        instance_id: 7,
        outcome_name: null,
        story_text: '',
        is_terminal: false,
        next_beat: null,
        epilogue: '',
      })
    );
    const { result } = renderHook(() => useResolveBeat(), { wrapper: wrapper() });
    await act(async () => {
      await result.current.mutateAsync({ instanceId: 7, option_id: 31 });
    });
    expect(calledUrls()).toContain('/api/missions/journal/7/resolve/?entry_id=5');
  });

  it('useTakeBoardPosting POSTs to a ?entry_id URL, bare when null', async () => {
    identity(5);
    apiFetch.mockResolvedValue(jsonResponse({ instance_id: 1, template_id: 2 }));
    const { result } = renderHook(() => useTakeBoardPosting(31), { wrapper: wrapper() });
    await act(async () => {
      await result.current.mutateAsync(2);
    });
    expect(calledUrls()).toContain('/api/missions/boards/31/take/?entry_id=5');

    apiFetch.mockClear();
    identity(null);
    const { result: bare } = renderHook(() => useTakeBoardPosting(31), { wrapper: wrapper() });
    await act(async () => {
      await bare.current.mutateAsync(2);
    });
    expect(calledUrls()).toContain('/api/missions/boards/31/take/');
    expect(calledUrls().some((u) => u.includes('entry_id'))).toBe(false);
  });
});
