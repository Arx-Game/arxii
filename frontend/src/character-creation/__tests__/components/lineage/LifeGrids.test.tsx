/**
 * The life as an accordion (#4874, slice 9 of #4813): one stage open at a time, the
 * others folded to a heading and a count; one section open inside it, the others reading
 * their answers or the beat's own prompt with the first name; Unknown a mark on the stage;
 * a secret pick with a cover story; Description (Optional) per stage; grouped answers;
 * signed prices; a term's definition; a figure's name on a person card; the ledger rail;
 * the life so far. Every life still ends on the Recent History box (#4830), and a
 * beginning that strikes every stage shows its text where the stage rows would be.
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
    name: 'Early Upbringing',
    prompt: 'Where {name} grew up.',
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
    opener_label: 'Early Upbringing',
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
const picked = (id: number, offerId: number, rank = 1) => ({
  id,
  rank,
  offer_ids: [offerId],
  arrivals: ['choice'],
});

const stage = (name: string) => screen.getByRole('region', { name });
const section = (name: string) => screen.getByRole('article', { name });

describe('LifeGrids', () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    syncMutate.mockClear();
    draftDistinctions = [];
    pool = [
      beat({ beat_id: 1, answer_offer_ids: [10, 11, 12] }),
      beat({
        beat_id: 2,
        name: 'Influences',
        prompt: 'What shaped {name}.',
        life_stage: 'youth',
        selection: 'any',
        allowance: null,
        answer_offer_ids: [20],
      }),
      beat({
        beat_id: 3,
        name: 'Known for',
        prompt: 'What they said of {name}.',
        life_stage: 'adulthood',
        selection: 'any',
        allowance: 2,
        answer_offer_ids: [30, 31, 32],
      }),
      beat({
        beat_id: 4,
        name: 'What marked it',
        prompt: 'What marked those years.',
        life_stage: 'adulthood',
        selection: 'any',
        allowance: null,
        answer_offer_ids: [],
      }),
    ];
    offersResponse = {
      offers: [
        offer({
          offer_id: 10,
          distinction_id: 100,
          name: 'Patient',
          effects: [{ target: 'sailing', label: 'sailing', value: 10, immune: false }],
        }),
        offer({
          offer_id: 11,
          distinction_id: 101,
          name: 'Spoiled',
          distinction_name: 'Soft Hands',
          cost_per_rank: -10,
        }),
        offer({ offer_id: 12, distinction_id: 102, name: 'Unremarkable', cost_per_rank: 0 }),
        offer({
          offer_id: 20,
          distinction_id: 200,
          name: 'Rival',
          cost_per_rank: 5,
          opener_key: 'beat:2',
          asks_figure_name: true,
        }),
        offer({
          offer_id: 30,
          distinction_id: 300,
          name: 'Spied for a house',
          opener_key: 'beat:3',
          group: 'Treatment',
        }),
        offer({
          offer_id: 31,
          distinction_id: 301,
          name: 'Killed for coin',
          opener_key: 'beat:3',
          group: 'Treatment',
        }),
        offer({ offer_id: 32, distinction_id: 302, name: 'Kept a shop', opener_key: 'beat:3' }),
      ],
      closed: [],
      terms: [{ name: 'sailing', label: 'sailing', definition: 'Handling a ship at sea.' }],
    };
  });

  it('opens on the first stage and its first section, the rest folded to a heading and a count', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft({ draft_data: { first_name: 'Marisol' } })} copy={{}} />
    );
    expect(screen.getByRole('heading', { name: 'Life So Far' })).toBeInTheDocument();
    expect(screen.getByText(/best describes Marisol’s life up to now/)).toBeInTheDocument();
    expect(stage('Childhood')).toHaveAttribute('data-open', 'true');
    expect(section('Early Upbringing')).toHaveAttribute('data-open', 'true');
    expect(within(section('Early Upbringing')).getByRole('list')).toHaveClass('grid', 'oneof');
    // A one-of row says no "pick one"; the open prompt reads the name.
    expect(screen.queryByText('pick one')).toBeNull();
    expect(
      within(section('Early Upbringing')).getByText('Where Marisol grew up.', {
        selector: '.beat-prompt',
      })
    ).toBeInTheDocument();
    const youth = stage('Youth');
    expect(youth).toHaveAttribute('data-open', 'false');
    expect(within(youth).getByText('0 of 1')).toBeInTheDocument();
    expect(within(youth).queryByRole('article')).toBeNull();
    const before = stage('Before the Glimpse');
    expect(within(before).getByText('0 of 2')).toBeInTheDocument();
    await user.click(within(before).getByRole('button', { name: /Before the Glimpse/ }));
    expect(stage('Before the Glimpse')).toHaveAttribute('data-open', 'true');
    expect(stage('Childhood')).toHaveAttribute('data-open', 'false');
    expect(section('Known for')).toHaveAttribute('data-open', 'true');
    expect(within(section('Known for')).getByText(/pick up to 2/)).toBeInTheDocument();
    expect(section('What marked it')).toHaveAttribute('data-open', 'false');
    expect(within(section('What marked it')).getByText('What marked those years.')).toHaveClass(
      'ans',
      'none'
    );
    // The open section folds on its own header; the open stage folds on its own too.
    await user.click(screen.getByTestId('sec-3'));
    expect(section('Known for')).toHaveAttribute('data-open', 'false');
    expect(section('What marked it')).toHaveAttribute('data-open', 'false');
    await user.click(screen.getByRole('button', { name: /^Before the Glimpse/ }));
    expect(stage('Before the Glimpse')).toHaveAttribute('data-open', 'false');
    expect(screen.queryAllByRole('article')).toHaveLength(0);
  });

  it('a closed section reads its answers with their signed points', async () => {
    const user = userEvent.setup();
    draftDistinctions = [picked(101, 11), picked(300, 30)];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    expect(within(stage('Childhood')).getByText('1 of 1')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /^Before the Glimpse/ }));
    // Next walks down: Known for closes to its answer and points, What marked it opens.
    await user.click(within(section('Known for')).getByRole('button', { name: 'Next' }));
    const known = section('Known for');
    expect(known).toHaveAttribute('data-open', 'false');
    expect(within(known).getByText('Spied for a house')).toHaveClass('ans');
    expect(within(known).getByText('\u221210')).toHaveClass('cost');
    expect(section('What marked it')).toHaveAttribute('data-open', 'true');
    // Back on Childhood, Next on its only section opens Youth and folds Childhood.
    await user.click(screen.getByRole('button', { name: /^Childhood/ }));
    await user.click(within(section('Early Upbringing')).getByRole('button', { name: 'Next' }));
    expect(stage('Youth')).toHaveAttribute('data-open', 'true');
    expect(screen.queryByRole('article', { name: 'Early Upbringing' })).toBeNull();
  });

  it('Next on the last section of a stage opens the next stage', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    await user.click(within(section('Early Upbringing')).getByRole('button', { name: 'Next' }));
    expect(stage('Youth')).toHaveAttribute('data-open', 'true');
    expect(section('Influences')).toHaveAttribute('data-open', 'true');
    expect(stage('Childhood')).toHaveAttribute('data-open', 'false');
  });

  it('a one-of pick drops the sibling already held on that beat', async () => {
    const user = userEvent.setup();
    draftDistinctions = [picked(100, 10)];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    await user.click(within(section('Early Upbringing')).getByRole('button', { name: /^Spoiled/ }));
    expect(syncMutate).toHaveBeenCalledWith([
      { id: 101, rank: 1, offer_id: 11, feature_trait: '', feature_marking: 0 },
    ]);
  });

  it('at its allowance an age-scaled beat lets the rest wait', async () => {
    const user = userEvent.setup();
    draftDistinctions = [picked(300, 30), picked(301, 31)];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    await user.click(screen.getByRole('button', { name: /^Before the Glimpse/ }));
    const known = section('Known for');
    expect(within(known).getByRole('button', { name: /^Kept a shop/ })).toBeDisabled();
    expect(within(known).getByRole('button', { name: /^Spied for a house/ })).toBeEnabled();
    expect(screen.getByText(/^1 taken, \d+ of \d+ points spent$/)).toBeInTheDocument();
  });

  it('answers with a group read under headings with counts, the ungrouped last', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    await user.click(screen.getByRole('button', { name: /^Before the Glimpse/ }));
    const known = section('Known for');
    const groups = known.querySelectorAll('.offer-group');
    expect(groups).toHaveLength(2);
    expect(within(groups[0] as HTMLElement).getByText('Treatment (2)')).toHaveClass('group-h');
    expect(within(groups[0] as HTMLElement).getByRole('button', { name: /^Killed for coin/ }));
    expect(groups[1].querySelector('.group-h')).toBeNull();
    expect(within(groups[1] as HTMLElement).getByRole('button', { name: /^Kept a shop/ }));
  });

  it('a grid card wears a signed price, a free card none, and its terms open their definition', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const early = section('Early Upbringing');
    const patient = within(early).getByRole('button', { name: /^Patient/ });
    expect(within(patient).getByText('−10')).toHaveClass('cost');
    expect(
      within(within(early).getByRole('button', { name: /^Spoiled/ })).getByText('+10')
    ).toHaveClass('award');
    const free = within(early).getByRole('button', { name: /Unremarkable/ });
    expect(free.querySelector('.price')?.textContent).toBe('');
    expect(within(patient).getByText('+10', { exact: false })).toBeInTheDocument();
    await user.click(within(patient).getByRole('button', { name: 'sailing, definition' }));
    const popover = screen.getByRole('dialog', { name: 'sailing' });
    expect(popover).toHaveTextContent('Handling a ship at sea.');
    // The term click is not a pick.
    expect(syncMutate).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('the stage mark sets every beat of the stage unknown in one save and folds it', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft();
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    await user.click(screen.getByRole('button', { name: /^Before the Glimpse/ }));
    await user.click(screen.getByRole('button', { name: 'Unknown: Before the Glimpse' }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '3': { unknown: true }, '4': { unknown: true } } } },
    });
    pool = pool.map((b) => (b.life_stage === 'adulthood' ? { ...b, unknown: true } : b));
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const before = screen.getAllByRole('region', { name: 'Before the Glimpse' }).at(-1)!;
    expect(within(before).getByText('Unknown', { selector: '.prog' })).toBeInTheDocument();
    await user.click(within(before).getByRole('button', { name: /^Before the Glimpse/ }));
    expect(within(before).queryByRole('article')).toBeNull();
    expect(within(before).queryByLabelText('Description (Optional)')).toBeNull();
    expect(
      within(before).getByRole('button', { name: 'Unknown: Before the Glimpse' })
    ).toHaveAttribute('aria-pressed', 'true');
  });

  it('a secret pick on a one-of row opens the Cover story box and the next card becomes the cover', async () => {
    const user = userEvent.setup();
    draftDistinctions = [picked(100, 10)];
    let draft = createMockDraft();
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const early = section('Early Upbringing');
    expect(screen.queryByText('Cover story')).toBeNull();
    await user.click(within(early).getByRole('button', { name: 'Secret: Patient' }));
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '1': { secret_offer_ids: [10] } } } },
    });

    draft = createMockDraft({ draft_data: { beats: { '1': { secret_offer_ids: [10] } } } });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const open = screen.getAllByRole('article', { name: 'Early Upbringing' }).at(-1)!;
    expect(
      within(open).getByText('Cover story', { selector: '.cover-box label' })
    ).toBeInTheDocument();
    // The secret pick says so on its card; the row's no-cost card stands as the cover
    // until another is chosen, drawn dashed and labelled.
    expect(
      within(within(open).getByRole('button', { name: /^Patient/ })).getByText(
        'Secret: select a cover story below'
      )
    ).toHaveClass('secret');
    const unremarkable = within(open).getByRole('button', { name: /^Unremarkable/ });
    expect(unremarkable).toHaveClass('cover');
    expect(within(unremarkable).getByText('Cover story')).toHaveClass('secret');
    expect(within(open).getByText('Unremarkable', { selector: '.cover-val' })).toBeInTheDocument();
    expect(within(open).getByText('Patient (secret; cover: Unremarkable)')).toHaveClass('ans');
    await user.click(within(open).getByRole('button', { name: /^Spoiled/ }));
    expect(syncMutate).not.toHaveBeenCalled();
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '1': { secret_offer_ids: [10], cover_offer_id: 11 } } } },
    });

    draft = createMockDraft({
      draft_data: { beats: { '1': { secret_offer_ids: [10], cover_offer_id: 11 } } },
    });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const covered = screen.getAllByRole('article', { name: 'Early Upbringing' }).at(-1)!;
    expect(within(covered).getByRole('button', { name: /^Spoiled/ })).toHaveClass('cover');
    expect(within(covered).getByRole('button', { name: /^Unremarkable/ })).not.toHaveClass('cover');
    expect(within(covered).getByText('Spoiled', { selector: '.cover-val' })).toBeInTheDocument();
    // Clicking the real pick again drops the secret and the cover; the pick stays.
    await user.click(within(covered).getByRole('button', { name: /^Patient/ }));
    expect(syncMutate).not.toHaveBeenCalled();
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '1': { secret_offer_ids: [], cover_offer_id: null } } } },
    });
  });

  it('on an any row the cover is a select of the unpicked answers', async () => {
    const user = userEvent.setup();
    draftDistinctions = [picked(300, 30)];
    const draft = createMockDraft({
      draft_data: { beats: { '3': { secret_offer_ids: [30] } } },
    });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    await user.click(screen.getByRole('button', { name: /^Before the Glimpse/ }));
    const select = within(section('Known for')).getByLabelText('Cover story');
    expect(
      within(select)
        .getAllByRole('option')
        .map((o) => o.textContent)
    ).toEqual(['Nothing shown', 'Killed for coin', 'Kept a shop']);
    await user.selectOptions(select, '31');
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '3': { secret_offer_ids: [30], cover_offer_id: 31 } } } },
    });
  });

  it('a person card takes the figure’s name once picked', async () => {
    const user = userEvent.setup();
    draftDistinctions = [picked(200, 20)];
    const draft = createMockDraft();
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    await user.click(screen.getByRole('button', { name: /^Youth/ }));
    const name = within(section('Influences')).getByLabelText('Rival: their name');
    expect(name).toHaveAttribute('maxlength', '60');
    await user.type(name, 'Ser Gaston');
    await user.tab();
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '2': { figures: { '20': 'Ser Gaston' } } } } },
    });
  });

  it('each stage ends on Description (Optional), saved on blur with the other stages kept', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ draft_data: { stage_descriptions: { youth: 'Wild years.' } } });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const box = within(stage('Childhood')).getByLabelText('Description (Optional)');
    expect(box).toHaveAttribute('maxlength', '1000');
    await user.click(box);
    await user.tab();
    expect(mutateAsync).not.toHaveBeenCalled();
    await user.type(box, 'Soft hands, hard lessons.');
    await user.tab();
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: {
        draft_data: {
          stage_descriptions: { youth: 'Wild years.', childhood: 'Soft hands, hard lessons.' },
        },
      },
    });
    expect(screen.queryByLabelText(/in your words/)).toBeNull();
  });

  it('the ledger rail lists the purse and every pick under its stage, and the life so far', async () => {
    draftDistinctions = [picked(101, 11), picked(300, 30)];
    // The purse reads the demo's way: the net points moved, Spent when positive and
    // Gained when the world paid more than it took.
    const draft = createMockDraft({
      cg_points_spent: -5,
      cg_points_remaining: 105,
      draft_data: { beats: { '3': { secret_offer_ids: [30] } } },
    });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const ledger = screen.getByRole('complementary', { name: 'CG points' });
    const totals = Array.from(ledger.querySelectorAll('.tot')).map((el) => el.textContent);
    expect(totals).toEqual(['Starting100', 'Spent0', 'Gained5', 'Remaining105']);
    const rows = Array.from(ledger.querySelectorAll('.row')).map((el) => el.textContent);
    expect(rows).toEqual(['Spoiled+10', 'Spied for a house (secret)−10']);
    expect(Array.from(ledger.querySelectorAll('.st')).map((el) => el.textContent)).toEqual([
      'Childhood',
      'Before the Glimpse',
    ]);
    const testament = document.querySelector('.testament')!;
    expect(testament.textContent).toBe(
      'Spoiled. Spied for a house (secret; cover: Nothing shown).'
    );
    expect(Array.from(testament.querySelectorAll('b')).map((b) => b.textContent)).toEqual([
      'Spoiled',
      'Spied for a house (secret; cover: Nothing shown)',
    ]);
  });

  it('with nothing chosen the rail and the life so far say so', () => {
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    expect(screen.getByText('Nothing chosen yet.')).toHaveClass('empty');
    expect(screen.getByText('Nothing written yet.')).toHaveClass('testament');
    expect(screen.getByText(/^0 taken, \d+ of \d+ points spent$/)).toBeInTheDocument();
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
    expect(at).toBeGreaterThan(order.lastIndexOf('stage-acc'));
    expect(at).toBeLessThan(order.indexOf('life-foot'));
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
