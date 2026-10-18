/**
 * The life as grids by stage (#4395): each beat a grid of its answers picked straight
 * from the cards, a one-of swapping its sibling, an age-scaled beat holding to its
 * allowance, the line of the player's own once something is picked, the unknown mark
 * closing a beat's answers, and a struck stage simply absent.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { LifeGrids } from '../../../components/lineage/LifeGrids';
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
    allowance: 1,
    ...over,
  };
}
function offer(over: Partial<VisibleOffer>): VisibleOffer {
  return {
    offer_id: 10,
    distinction_id: 100,
    name: 'Patient',
    distinction_name: 'Patient',
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

describe('LifeGrids', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    syncMutate.mockClear();
    draftDistinctions = [];
    pool = [
      beat({ beat_id: 1, name: 'The household', answer_offer_ids: [10, 11] }),
      beat({
        beat_id: 3,
        name: 'Known for',
        life_stage: 'adulthood',
        selection: 'any',
        allowance: 2,
        answer_offer_ids: [30, 31, 32],
      }),
      beat({
        beat_id: 4,
        name: 'What marked it',
        life_stage: 'adulthood',
        selection: 'any',
        allowance: null,
        answer_offer_ids: [],
      }),
    ];
    offersResponse = {
      offers: [
        offer({ offer_id: 10, distinction_id: 100, name: 'Patient' }),
        offer({
          offer_id: 11,
          distinction_id: 101,
          name: 'Spoiled',
          distinction_name: 'Soft Hands',
          cost_per_rank: -10,
        }),
        offer({
          offer_id: 30,
          distinction_id: 300,
          name: 'Spied for a house',
          opener_key: 'beat:3',
        }),
        offer({ offer_id: 31, distinction_id: 301, name: 'Killed for coin', opener_key: 'beat:3' }),
        offer({ offer_id: 32, distinction_id: 302, name: 'Kept a shop', opener_key: 'beat:3' }),
      ],
      closed: [],
    };
  });

  it('draws each stage as a block of grids with its pick line, and no struck stage', () => {
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const childhood = screen.getByRole('region', { name: 'Childhood' });
    const household = within(childhood).getByRole('article', { name: 'The household' });
    expect(within(household).getByRole('list')).toHaveClass('grid', 'oneof');
    expect(within(household).getByText('pick one')).toBeInTheDocument();
    // The card reads the offer's label and the distinction under it when they differ.
    const spoiled = within(household).getByRole('button', { name: /Spoiled/ });
    expect(within(spoiled).getByText('Soft Hands')).toBeInTheDocument();
    const before = screen.getByRole('region', { name: 'Before the Glimpse' });
    const known = within(before).getByRole('article', { name: 'Known for' });
    expect(within(known).getByRole('list')).toHaveClass('grid');
    expect(within(known).getByRole('list')).not.toHaveClass('oneof');
    expect(
      within(known).getByText('pick up to 2; an older character takes more')
    ).toBeInTheDocument();
    expect(within(before).getByText('pick any')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Youth' })).toBeNull();
    expect(screen.getByText(/^0 taken, \d+ of \d+ points spent$/)).toBeInTheDocument();
  });

  it('a one-of pick drops the sibling already held on that beat', async () => {
    const user = userEvent.setup();
    draftDistinctions = [{ id: 100, rank: 1, offer_ids: [10], arrivals: ['choice'] }];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const household = screen.getByRole('article', { name: 'The household' });
    await user.click(within(household).getByRole('button', { name: /Spoiled/ }));
    expect(syncMutate).toHaveBeenCalledWith([
      { id: 101, rank: 1, offer_id: 11, feature_trait: '', feature_marking: 0 },
    ]);
  });

  it('at its allowance an age-scaled beat lets the rest wait', () => {
    draftDistinctions = [
      { id: 300, rank: 1, offer_ids: [30], arrivals: ['choice'] },
      { id: 301, rank: 1, offer_ids: [31], arrivals: ['choice'] },
    ];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const known = screen.getByRole('article', { name: 'Known for' });
    expect(within(known).getByRole('button', { name: /Kept a shop/ })).toBeDisabled();
    expect(within(known).getByRole('button', { name: /Spied for a house/ })).toBeEnabled();
    // Two picks on one beat: one beat taken.
    expect(screen.getByText(/^1 taken, \d+ of \d+ points spent$/)).toBeInTheDocument();
  });

  it('a pick opens the line of your own words, which saves the whole beats map', async () => {
    const user = userEvent.setup();
    draftDistinctions = [{ id: 100, rank: 1, offer_ids: [10], arrivals: ['choice'] }];
    const draft = createMockDraft({ draft_data: { beats: { '3': { line: 'x' } } } });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const household = screen.getByRole('article', { name: 'The household' });
    const line = within(household).getByLabelText('The household, in your words');
    await user.type(line, 'Soft hands, hard lessons.');
    await user.tab();
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: {
        draft_data: {
          beats: { '3': { line: 'x' }, '1': { line: 'Soft hands, hard lessons.' } },
        },
      },
    });
    const known = screen.getByRole('article', { name: 'Known for' });
    expect(within(known).queryByLabelText(/in your words/)).toBeNull();
  });

  it('the unknown mark keeps the beat and closes its answers', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft();
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const household = screen.getByRole('article', { name: 'The household' });
    await user.click(within(household).getByRole('button', { name: 'Unknown: The household' }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '1': { unknown: true } } } },
    });
    pool = pool.map((b) => (b.beat_id === 1 ? { ...b, unknown: true } : b));
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const unknownHousehold = screen.getAllByRole('article', { name: 'The household' }).at(-1)!;
    expect(within(unknownHousehold).queryByRole('button', { name: /Patient/ })).toBeNull();
  });
});
