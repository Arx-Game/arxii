/**
 * The save of a draft's distinction picks (#5134).
 *
 * A card click used to wait on two requests: the save, then a second request for
 * the list the save had already returned. And a second card grid on the same page
 * could not tell a save was in flight, so its next save was computed from the list
 * about to be replaced.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { distinctionKeys, usePendingSync, useSyncDistinctions } from '../useDistinctions';
import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';

const DRAFT_ID = 7;
const picks: SyncDistinctionEntry[] = [
  { id: 1, rank: 1, offer_id: 101, feature_trait: '', feature_marking: 0 },
];
const saved: DraftDistinctionEntry[] = [
  {
    distinction_id: 1,
    distinction_name: 'Silver Tongue',
    distinction_slug: 'silver-tongue',
    category_slug: 'social',
    rank: 1,
    cost: 10,
    notes: '',
    offer_ids: [101],
    sources: ['Mark'],
    arrivals: ['choice'],
  },
];

function setUp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  queryClient.setQueryData(distinctionKeys.draftDistinctions(DRAFT_ID), []);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, wrapper };
}

describe('useSyncDistinctions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("puts the save's own answer in the list, and asks for the list no second time", async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ distinctions: saved, stat_adjustments: [] }),
    } as Response);
    const { queryClient, wrapper } = setUp();
    const { result } = renderHook(() => useSyncDistinctions(DRAFT_ID), { wrapper });

    act(() => result.current.mutate(picks));

    await waitFor(() =>
      expect(queryClient.getQueryData(distinctionKeys.draftDistinctions(DRAFT_ID))).toEqual(saved)
    );
    // One request: the PUT. Nothing went back for `/drafts/7/distinctions/`.
    expect(vi.mocked(apiFetch).mock.calls.map(([url]) => url)).toEqual([
      '/api/distinctions/drafts/7/distinctions/sync/',
    ]);
    await waitFor(() => expect(result.current.pendingEntries).toBeNull());
  });

  it('every grid on the page sees the picks a save in flight is writing', async () => {
    // A server that never answers: the save stays in flight.
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    const { wrapper } = setUp();
    // Two grids, each with its own mutation, and a bare reader.
    const { result } = renderHook(
      () => ({
        clicked: useSyncDistinctions(DRAFT_ID),
        other: useSyncDistinctions(DRAFT_ID),
        reader: usePendingSync(DRAFT_ID),
        elsewhere: usePendingSync(DRAFT_ID + 1),
      }),
      { wrapper }
    );
    expect(result.current.other.pendingEntries).toBeNull();

    act(() => result.current.clicked.mutate(picks));

    await waitFor(() => expect(result.current.clicked.pendingEntries).toEqual(picks));
    expect(result.current.other.pendingEntries).toEqual(picks);
    expect(result.current.other.isPending).toBe(false);
    expect(result.current.reader).toEqual(picks);
    // Another draft's grids are not held by it.
    expect(result.current.elsewhere).toBeNull();
  });

  it('a save that fails leaves the list as it was and lets the cards go', async () => {
    vi.mocked(apiFetch).mockResolvedValue({
      ok: false,
      json: () => Promise.resolve({ detail: 'At most one answer on The household.' }),
    } as Response);
    const { queryClient, wrapper } = setUp();
    const { result } = renderHook(() => useSyncDistinctions(DRAFT_ID), { wrapper });

    act(() => result.current.mutate(picks));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.pendingEntries).toBeNull();
    expect(queryClient.getQueryData(distinctionKeys.draftDistinctions(DRAFT_ID))).toEqual([]);
  });
});
