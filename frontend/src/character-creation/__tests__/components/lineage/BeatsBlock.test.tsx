/**
 * The beats of a life at Lineage (#4124): one block per stage, a taken beat's answers as
 * priced offers (one-of across, any-that-apply down), add / remove / unknown through one
 * `draft_data.beats` map, and a one-of pick dropping its sibling.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { BeatsBlock } from '../../../components/lineage/BeatsBlock';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import type { BeatPoolEntry, OffersResponse, VisibleOffer } from '../../../types';

const mutateAsync = vi.fn().mockResolvedValue({});
const syncMutate = vi.fn();
let pool: BeatPoolEntry[] = [];
let offersResponse: OffersResponse = { offers: [], closed: [] };
let draftDistinctions: { id: number; rank: number; offer_ids: number[]; arrivals: string[] }[] = [];

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync }),
  useDraftBeats: () => ({ data: pool, isLoading: false }),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate: syncMutate, isPending: false, isError: false }),
}));

function beat(over: Partial<BeatPoolEntry>): BeatPoolEntry {
  return {
    beat_id: 1,
    name: 'The household',
    prompt: 'Placeholder prompt.',
    life_stage: 'childhood',
    selection: 'one_of',
    taken: false,
    unknown: false,
    line: '',
    answer_offer_ids: [],
    kept: false,
    ...over,
  };
}
function offer(over: Partial<VisibleOffer>): VisibleOffer {
  return {
    offer_id: 10,
    distinction_id: 100,
    name: 'Patient',
    player_line: '',
    chapter: 'backgrounds',
    arrives_as: 'choice',
    opener_label: 'The household',
    cost_per_rank: 10,
    max_rank: 1,
    is_locked: false,
    lock_reason: '',
    opener_key: 'beat:1',
    first_look: false,
    held: false,
    effect_line: '',
    taken_per_feature: false,
    opens_feature: false,
    requires_feature_opened: false,
    cg_max_rank: 0,
    ...over,
  };
}

describe('BeatsBlock', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    syncMutate.mockClear();
    draftDistinctions = [];
    offersResponse = { offers: [], closed: [] };
    pool = [
      beat({ beat_id: 1, name: 'The household', taken: true, answer_offer_ids: [10, 11] }),
      beat({ beat_id: 2, name: 'The first rule', life_stage: 'youth' }),
      beat({
        beat_id: 3,
        name: 'The work',
        life_stage: 'adulthood',
        selection: 'any',
        taken: true,
        answer_offer_ids: [30, 31],
      }),
    ];
    offersResponse = {
      offers: [
        offer({ offer_id: 10, distinction_id: 100, name: 'Patient' }),
        offer({ offer_id: 11, distinction_id: 101, name: 'Spoiled', cost_per_rank: -10 }),
        offer({ offer_id: 30, distinction_id: 300, name: 'Efficient', opener_key: 'beat:3' }),
        offer({ offer_id: 31, distinction_id: 301, name: 'Secretive', opener_key: 'beat:3' }),
      ],
      closed: [],
    };
  });

  it('draws a one-of beat across and an any-that-apply beat down, each stage its own block', () => {
    renderWithCharacterCreationProviders(<BeatsBlock draft={createMockDraft()} copy={{}} />);
    const household = screen.getByRole('article', { name: 'The household' });
    expect(within(household).getByRole('list')).toHaveClass('oneof');
    expect(within(household).getByRole('button', { name: /Patient/ })).toBeInTheDocument();
    const work = screen.getByRole('article', { name: 'The work' });
    expect(within(work).getByRole('list')).not.toHaveClass('oneof');
    // The untaken youth beat waits in its stage's pool.
    const youth = screen.getByRole('group', { name: /Youth/ });
    expect(within(youth).getByRole('button', { name: 'The first rule' })).toBeInTheDocument();
  });

  it('adding a beat sends the whole beats map with the beat taken', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      draft_data: { beats: { '1': { taken: true }, '3': { taken: true, line: 'x' } } },
    });
    renderWithCharacterCreationProviders(<BeatsBlock draft={draft} copy={{}} />);
    await user.click(screen.getByRole('button', { name: 'The first rule' }));
    expect(mutateAsync).toHaveBeenCalledWith({
      draftId: draft.id,
      data: {
        draft_data: {
          beats: {
            '1': { taken: true },
            '3': { taken: true, line: 'x' },
            '2': { taken: true, unknown: false },
          },
        },
      },
    });
  });

  it('removing a beat drops it from the map; unknown keeps it and hides its answers', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({
      draft_data: { beats: { '1': { taken: true }, '3': { taken: true } } },
    });
    renderWithCharacterCreationProviders(<BeatsBlock draft={draft} copy={{}} />);
    const work = screen.getByRole('article', { name: 'The work' });
    await user.click(within(work).getByRole('button', { name: 'Remove' }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '1': { taken: true } } } },
    });
    const household = screen.getByRole('article', { name: 'The household' });
    await user.click(within(household).getByRole('button', { name: 'Unknown: The household' }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: {
        draft_data: { beats: { '1': { taken: true, unknown: true }, '3': { taken: true } } },
      },
    });
    pool = pool.map((b) => (b.beat_id === 1 ? { ...b, unknown: true } : b));
    renderWithCharacterCreationProviders(<BeatsBlock draft={draft} copy={{}} />);
    const unknownHousehold = screen.getAllByRole('article', { name: 'The household' }).at(-1)!;
    expect(within(unknownHousehold).queryByRole('button', { name: /Patient/ })).toBeNull();
  });

  it('a one-of pick drops the sibling already held on that beat', async () => {
    const user = userEvent.setup();
    draftDistinctions = [{ id: 100, rank: 1, offer_ids: [10], arrivals: ['choice'] }];
    const draft = createMockDraft({ draft_data: { beats: { '1': { taken: true } } } });
    renderWithCharacterCreationProviders(<BeatsBlock draft={draft} copy={{}} />);
    const household = screen.getByRole('article', { name: 'The household' });
    await user.click(within(household).getByRole('button', { name: /Spoiled/ }));
    expect(syncMutate).toHaveBeenCalledWith([
      { id: 101, rank: 1, offer_id: 11, feature_trait: '', feature_marking: 0 },
    ]);
  });

  it('a kept beat has no remove', () => {
    pool = [beat({ beat_id: 9, name: 'Defining the Inexplicable', taken: true, kept: true })];
    renderWithCharacterCreationProviders(<BeatsBlock draft={createMockDraft()} copy={{}} />);
    const kept = screen.getByRole('article', { name: 'Defining the Inexplicable' });
    expect(within(kept).queryByRole('button', { name: 'Remove' })).toBeNull();
  });
});
