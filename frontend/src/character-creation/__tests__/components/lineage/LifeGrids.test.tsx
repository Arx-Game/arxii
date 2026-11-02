/**
 * The life as grids by stage (#4395): each beat a grid of its answers picked straight
 * from the cards, a one-of swapping its sibling, an age-scaled beat holding to its
 * allowance, the line of the player's own once something is picked, the unknown mark
 * closing a beat's answers, and a struck stage simply absent. Every life ends on the Recent
 * History box (#4830), and a beginning that strikes every stage shows its text where the
 * stage rows would be.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { LifeGrids } from '../../../components/lineage/LifeGrids';
import { createMockDraft, mockBeginnings, mockBeginningsUnknownFamily } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import type { BeatPoolEntry, OffersResponse, VisibleOffer } from '../../../types';

const mutateAsync = vi.fn().mockResolvedValue({});
const syncMutate = vi.fn();
const loadMutate = vi.fn();
const clearMutate = vi.fn();
let pool: BeatPoolEntry[] = [];
let offersResponse: OffersResponse = { offers: [], closed: [], terms: [] };
let draftDistinctions: { id: number; rank: number; offer_ids: number[]; arrivals: string[] }[] = [];

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync }),
  useLoadDefaultLife: () => ({ mutate: loadMutate, isPending: false }),
  useClearLife: () => ({ mutate: clearMutate, isPending: false }),
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
    allowance: 1,
    allowance_is_points: false,
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
    group: '',
    asks_figure_name: false,
    effects: [],
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
      terms: [],
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

  it('every life ends on the Recent History box, under the last stage, saved on blur', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ draft_data: { recent_history: 'A debt in Umbros.' } });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const box = screen.getByLabelText('Recent History (Optional)');
    expect(box).toHaveValue('A debt in Umbros.');
    expect(box).toHaveAttribute('maxlength', '2000');
    expect(
      screen.getByText('What you want a GM or another player to pick up.')
    ).toBeInTheDocument();
    const order = Array.from(box.closest('.life')!.children).map((el) => el.className);
    const at = order.indexOf('field recent-history');
    expect(at).toBeGreaterThan(order.lastIndexOf('life-stage'));
    expect(at).toBeLessThan(order.indexOf('life-foot'));
    // Leaving the box unchanged saves nothing; a new text saves on blur, by itself.
    await user.click(box);
    await user.tab();
    expect(mutateAsync).not.toHaveBeenCalled();
    await user.clear(box);
    await user.type(box, 'Someone is looking for a man with my name.');
    await user.tab();
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { recent_history: 'Someone is looking for a man with my name.' } },
    });
  });

  it('a beginning that strikes every stage shows its text where the stages were, then the box', () => {
    pool = [];
    const sleeper = {
      ...mockBeginningsUnknownFamily,
      strikes_childhood: true,
      strikes_youth: true,
      strikes_adulthood: true,
      struck_stages_text: 'You woke in a tomb that was not yours.',
    };
    const draft = createMockDraft({ selected_beginnings: sleeper });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const text = screen.getByText('You woke in a tomb that was not yours.');
    expect(text).toHaveClass('absent');
    expect(screen.queryAllByRole('region')).toHaveLength(0);
    expect(screen.queryByText(/pick one|pick any|pick up to/)).toBeNull();
    expect(screen.queryByText(/points spent$/)).toBeNull();
    const box = screen.getByLabelText('Recent History (Optional)');
    expect(text.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('a struck beginning with no text authored yet shows the fallback line', () => {
    pool = [];
    const sleeper = {
      ...mockBeginningsUnknownFamily,
      strikes_childhood: true,
      strikes_youth: true,
      strikes_adulthood: true,
      struck_stages_text: '',
    };
    renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft({ selected_beginnings: sleeper })} copy={{}} />
    );
    expect(
      screen.getByText('Every stage of this life is struck. What there is to say begins below.')
    ).toHaveClass('absent');
  });

  it('an empty pool on a beginning that keeps its stages shows the box alone', () => {
    pool = [];
    renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft({ selected_beginnings: mockBeginnings })} copy={{}} />
    );
    expect(screen.getByLabelText('Recent History (Optional)')).toBeInTheDocument();
    expect(document.querySelector('.absent')).toBeNull();
    expect(screen.queryByText(/points spent$/)).toBeNull();
  });
});

describe('LifeGrids (the suggested life, #4865)', () => {
  beforeEach(() => {
    loadMutate.mockClear();
    clearMutate.mockClear();
    pool = [beat({ beat_id: 1, name: 'The household' })];
    offersResponse = { offers: [offer({ offer_id: 10, name: 'Spoiled' })], closed: [], terms: [] };
    draftDistinctions = [];
  });

  it('loads the suggested life once when the grids open for a beginning the stamp does not name', () => {
    const { rerender } = renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft({ selected_beginnings: mockBeginnings })} copy={{}} />
    );
    expect(loadMutate).toHaveBeenCalledTimes(1);
    rerender(
      <LifeGrids draft={createMockDraft({ selected_beginnings: mockBeginnings })} copy={{}} />
    );
    expect(loadMutate).toHaveBeenCalledTimes(1);
  });

  it('loads nothing when the stamp names the beginning, or there is no beginning', () => {
    const { unmount } = renderWithCharacterCreationProviders(
      <LifeGrids
        draft={createMockDraft({
          selected_beginnings: mockBeginnings,
          draft_data: { life_loaded_for: mockBeginnings.id },
        })}
        copy={{}}
      />
    );
    expect(loadMutate).not.toHaveBeenCalled();
    unmount();
    renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft({ selected_beginnings: null })} copy={{}} />
    );
    expect(loadMutate).not.toHaveBeenCalled();
  });

  it('Start blank clears the life', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <LifeGrids
        draft={createMockDraft({
          selected_beginnings: mockBeginnings,
          draft_data: { life_loaded_for: mockBeginnings.id },
        })}
        copy={{}}
      />
    );
    await user.click(screen.getByRole('button', { name: 'Start blank' }));
    expect(clearMutate).toHaveBeenCalledTimes(1);
  });
});
