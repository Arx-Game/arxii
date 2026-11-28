/**
 * The CG points on screen across a save (#5141).
 *
 * The owner's report, after a clicked card began to show at once (#5134): "the CG point
 * total on the right is very slow to update, slow enough that it will cause confusion".
 * The totals read the draft, and the draft was fetched again only after the save had
 * answered. These tests run the real save and the real draft cache against a server
 * that does not answer when the test says so.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: vi.fn(),
}));

import { apiFetch } from '@/evennia_replacements/api';
import { distinctionKeys, useSyncDistinctions } from '@/hooks/useDistinctions';
import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';
import { characterCreationKeys } from '../queries';
import type { CharacterDraft } from '../types';
import { useShownPicks } from '../useShownPicks';
import { createMockDraft } from './fixtures';

const DRAFT_ID = 7;
const SYNC_URL = `/api/distinctions/drafts/${DRAFT_ID}/distinctions/sync/`;

function entry(over: Partial<DraftDistinctionEntry>): DraftDistinctionEntry {
  return {
    distinction_id: 1,
    distinction_name: 'Spoiled',
    distinction_slug: 'spoiled',
    category_slug: 'background',
    rank: 1,
    cost: -10,
    notes: '',
    offer_ids: [11],
    sources: ['The household'],
    arrivals: ['choice'],
    ...over,
  };
}
const row = (id: number, offerId: number): SyncDistinctionEntry => ({
  id,
  rank: 1,
  offer_id: offerId,
  feature_trait: '',
  feature_marking: 0,
});

// Held before the click: Spoiled, for which the world pays 10. The species costs 15
// more, so the server's totals read 5 spent of 100.
const spoiled = entry({});
// The click swaps Spoiled for Patient (offer 10, 10 points).
const patient = entry({
  distinction_id: 2,
  distinction_name: 'Patient',
  distinction_slug: 'patient',
  cost: 10,
  offer_ids: [10],
});
const click = [row(2, 10)];

/** A promise the test settles when it chooses. */
function held<T>() {
  let settle!: (value: T) => void;
  const promise = new Promise<T>((resolve) => {
    settle = resolve;
  });
  return { promise, settle };
}

function setUp() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity, staleTime: Infinity } },
  });
  const draft = createMockDraft({
    id: DRAFT_ID,
    cg_points_spent: 5,
    cg_points_remaining: 95,
    draft_data: { distinctions: [spoiled] },
  });
  queryClient.setQueryData(characterCreationKeys.draft(), draft);
  queryClient.setQueryData(distinctionKeys.draftDistinctions(DRAFT_ID), [spoiled]);
  queryClient.setQueryData(characterCreationKeys.draftOffers(DRAFT_ID, 'backgrounds'), {
    offers: [
      { offer_id: 11, cost_per_rank: -10 },
      { offer_id: 10, cost_per_rank: 10 },
    ],
    terms: [],
    glimpse_cards: [],
  });
  // The draft fetch the save sets off. It answers only when the test settles it.
  const draftFetch = held<CharacterDraft>();
  const fetchDraft = vi.fn(() => draftFetch.promise);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  const view = renderHook(
    () => {
      const { data } = useQuery({ queryKey: characterCreationKeys.draft(), queryFn: fetchDraft });
      return { sync: useSyncDistinctions(DRAFT_ID), shown: useShownPicks(data ?? draft) };
    },
    { wrapper }
  );
  return { queryClient, view, draftFetch, fetchDraft };
}

const totals = (shown: { spent: number; remaining: number }) => [shown.spent, shown.remaining];

describe('useShownPicks', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("with no save in flight the totals are the server's own", () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    const { view } = setUp();
    expect(totals(view.result.current.shown)).toEqual([5, 95]);
    expect(view.result.current.shown.picks.map((p) => p.distinction_id)).toEqual([1]);
  });

  it('the totals move with the click, before the save has answered', async () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    const { view, fetchDraft } = setUp();

    act(() => view.result.current.sync.mutate(click));

    // Spoiled's 10 is no longer paid to the character and Patient's 10 is spent:
    // 5 + 10 + 10 = 25 of the 100.
    await waitFor(() => expect(totals(view.result.current.shown)).toEqual([25, 75]));
    expect(view.result.current.shown.picks.map((p) => [p.distinction_id, p.cost])).toEqual([
      [2, 10],
    ]);
    // Nothing has answered: one request, the save, and no draft fetch at all.
    expect(vi.mocked(apiFetch).mock.calls.map(([url]) => url)).toEqual([SYNC_URL]);
    expect(fetchDraft).not.toHaveBeenCalled();
  });

  it('a feature quality inside the free allowance moves no CG points (#5241)', async () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    const { queryClient, view } = setUp();
    queryClient.setQueryData(characterCreationKeys.draftOffers(DRAFT_ID, 'appearance'), {
      offers: [{ offer_id: 90, cost_per_rank: 1 }],
      terms: [],
      glimpse_cards: [],
    });
    const tiers = (rank: number): SyncDistinctionEntry[] => [
      row(1, 11),
      { id: 9, rank, offer_id: 90, feature_trait: 'hair_color', feature_marking: 0 },
    ];

    act(() => view.result.current.sync.mutate(tiers(3)));

    // Three tiers of the ten that are free: the feature points move, the CG points do not.
    await waitFor(() => expect(view.result.current.shown.featureSpent).toBe(3));
    expect(totals(view.result.current.shown)).toEqual([5, 95]);
  });

  it('feature qualities past the free allowance cost CG points (#5241)', async () => {
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}));
    const { queryClient, view } = setUp();
    queryClient.setQueryData(characterCreationKeys.draftOffers(DRAFT_ID, 'appearance'), {
      offers: [{ offer_id: 90, cost_per_rank: 1 }],
      terms: [],
      glimpse_cards: [],
    });

    act(() =>
      view.result.current.sync.mutate([
        row(1, 11),
        { id: 9, rank: 12, offer_id: 90, feature_trait: 'hair_color', feature_marking: 0 },
      ])
    );

    // Twelve points of qualities, ten of them free: two CG points on top of the 5.
    await waitFor(() => expect(view.result.current.shown.featureSpent).toBe(12));
    expect(totals(view.result.current.shown)).toEqual([7, 93]);
  });

  it('when the save answers the totals stand, with the draft fetch still out', async () => {
    const save = held<Response>();
    vi.mocked(apiFetch).mockReturnValue(save.promise);
    const { queryClient, view, draftFetch, fetchDraft } = setUp();

    act(() => view.result.current.sync.mutate(click));
    await waitFor(() => expect(totals(view.result.current.shown)).toEqual([25, 75]));

    // The server charged 12 for Patient, not the 10 its offer named.
    const charged = { ...patient, cost: 12 };
    await act(async () => {
      save.settle({
        ok: true,
        json: () => Promise.resolve({ distinctions: [charged], stat_adjustments: [] }),
      } as Response);
    });

    await waitFor(() => expect(view.result.current.sync.pendingEntries).toBeNull());
    // The draft fetch has been asked for and has not answered; the totals already read
    // the save's own prices.
    expect(fetchDraft).toHaveBeenCalledTimes(1);
    expect(totals(view.result.current.shown)).toEqual([27, 73]);
    const cached = queryClient.getQueryData<CharacterDraft>(characterCreationKeys.draft());
    expect(cached?.draft_data.distinctions).toEqual([charged]);

    // The server's own figures replace the page's arithmetic when the fetch lands.
    await act(async () => {
      draftFetch.settle(
        createMockDraft({
          id: DRAFT_ID,
          cg_points_spent: 30,
          cg_points_remaining: 70,
          draft_data: { distinctions: [charged] },
        })
      );
    });
    await waitFor(() => expect(totals(view.result.current.shown)).toEqual([30, 70]));
  });

  it('a save that fails puts the old totals back', async () => {
    const save = held<Response>();
    vi.mocked(apiFetch).mockReturnValue(save.promise);
    const { view, fetchDraft } = setUp();

    act(() => view.result.current.sync.mutate(click));
    await waitFor(() => expect(totals(view.result.current.shown)).toEqual([25, 75]));

    await act(async () => {
      save.settle({
        ok: false,
        json: () => Promise.resolve({ detail: 'At most one answer on The household.' }),
      } as Response);
    });

    await waitFor(() => expect(view.result.current.sync.isError).toBe(true));
    expect(totals(view.result.current.shown)).toEqual([5, 95]);
    expect(view.result.current.shown.picks.map((p) => p.distinction_id)).toEqual([1]);
    expect(fetchDraft).not.toHaveBeenCalled();
  });
});
