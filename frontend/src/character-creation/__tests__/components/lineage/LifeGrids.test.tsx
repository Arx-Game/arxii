/**
 * The life as folds (#4874, slice 9 of #4813): every stage and every section open on
 * arrival, each folding by itself (#5160); a folded stage a heading and a count, a folded
 * section its answers or the beat's own prompt with the first name; Unknown a mark on the
 * stage; a secret pick with a cover story; grouped answers; signed prices; a term's
 * definition; a figure's name on a person card; the choices list; the life so far. The
 * page holds no free-text box about the life (#5178: the Background is one box on Final
 * Touches), and a beginning that strikes every stage shows its text and nothing else.
 */
import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { LifeGrids } from '../../../components/lineage/LifeGrids';
import { ChapterLeaf } from '../../../folio';
import { createMockDraft, mockBeginnings, mockBeginningsUnknownFamily } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import { Stage, type BeatPoolEntry, type OffersResponse, type VisibleOffer } from '../../../types';
import { characterCreationKeys } from '../../../queries';
import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';
import { QueryClient } from '@tanstack/react-query';

const mutateAsync = vi.fn().mockResolvedValue({});
const syncMutate = vi.fn();
const loadMutate = vi.fn();
let pool: BeatPoolEntry[] = [];
let offersResponse: OffersResponse = { offers: [], terms: [] };
let draftDistinctions: {
  id: number;
  distinction_id?: number;
  rank: number;
  cost?: number;
  offer_ids: number[];
  arrivals: string[];
}[] = [];
// The picks a save in flight is writing (#5141), null when none is.
let pendingSync: SyncDistinctionEntry[] | null = null;

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync }),
  useLoadDefaultLife: () => ({ mutate: loadMutate, isPending: false }),
  useDraftBeats: () => ({ data: pool, isLoading: false }),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate: syncMutate, isPending: false, isError: false }),
  usePendingSync: () => pendingSync,
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
    distinction_description: '',
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
    pendingSync = null;
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
          // The offer's own line repeats the name, as the authored rows do (#5099).
          player_line: 'Patient',
          distinction_description: 'You learned to wait out every storm.',
          effects: [{ target: 'sailing', label: 'sailing', value: 10, immune: false }],
        }),
        offer({
          offer_id: 11,
          distinction_id: 101,
          name: 'Spoiled',
          distinction_name: 'Soft Hands',
          distinction_description: '',
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
      terms: [{ name: 'sailing', label: 'sailing', definition: 'Handling a ship at sea.' }],
    };
  });

  it('opens with every stage and every section expanded (#5160)', () => {
    renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft({ draft_data: { first_name: 'Marisol' } })} copy={{}} />
    );
    // The life's own heading; the list of choices carries the same words as its label.
    expect(screen.getAllByRole('heading', { name: 'Life So Far' })[0]).toHaveClass('section-h');
    expect(
      screen.getByText(
        /^In this stage, distinctions can be selected that best describe Marisol’s life up to now\./
      )
    ).toBeInTheDocument();
    for (const name of ['Childhood', 'Youth', 'Before the Glimpse']) {
      expect(stage(name)).toHaveAttribute('data-open', 'true');
      expect(
        within(stage(name)).getByRole('button', { name: new RegExp(`^${name}`) })
      ).toHaveAttribute('aria-expanded', 'true');
    }
    for (const name of ['Early Upbringing', 'Influences', 'Known for', 'What marked it']) {
      expect(section(name)).toHaveAttribute('data-open', 'true');
      // An open section shows its grid and no Next of its own: the fold arrow at its
      // heading closes it, and the page's Next is the only Next (#5201).
      expect(within(section(name)).queryByRole('button', { name: 'Next' })).toBeNull();
    }
    expect(within(section('Early Upbringing')).getByRole('list')).toHaveClass('grid', 'oneof');
    // Every section's cards are on the page without a click.
    expect(screen.getByRole('button', { name: /^Patient/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Rival/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^Kept a shop/ })).toBeInTheDocument();
    // A one-of row says no "pick one"; the open prompt reads the name.
    expect(screen.queryByText('pick one')).toBeNull();
    expect(
      within(section('Early Upbringing')).getByText('Where Marisol grew up.', {
        selector: '.beat-prompt',
      })
    ).toBeInTheDocument();
    expect(within(section('Known for')).getByText(/pick up to 2/)).toBeInTheDocument();
    // An open section prints its prompt once, in its body, not again on its line.
    expect(within(section('Known for')).getAllByText('What they said of Marisol.')).toHaveLength(1);
    expect(screen.getByTestId('sec-3').querySelector('.ans')).toBeNull();
    // Each stage still counts its answered sections beside its heading.
    expect(within(stage('Youth')).getByText('0 of 1')).toBeInTheDocument();
    expect(within(stage('Before the Glimpse')).getByText('0 of 2')).toBeInTheDocument();
  });

  it('a fold closes and opens by itself and moves no other fold (#5160)', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    // A section folds on its own line: its prompt stands in for the grid, and the
    // section beside it, the other stages and their sections stay as they were.
    await user.click(screen.getByTestId('sec-3'));
    expect(section('Known for')).toHaveAttribute('data-open', 'false');
    expect(screen.getByTestId('sec-3')).toHaveAttribute('aria-expanded', 'false');
    expect(within(section('Known for')).queryByRole('list')).toBeNull();
    expect(within(section('Known for')).getByText('What they said of you.')).toHaveClass(
      'ans',
      'none'
    );
    expect(section('What marked it')).toHaveAttribute('data-open', 'true');
    expect(section('Early Upbringing')).toHaveAttribute('data-open', 'true');
    expect(section('Influences')).toHaveAttribute('data-open', 'true');
    // A stage folds to its heading and count; the others keep their sections.
    await user.click(screen.getByRole('button', { name: /^Youth/ }));
    const youth = stage('Youth');
    expect(youth).toHaveAttribute('data-open', 'false');
    expect(within(youth).getByText('0 of 1')).toBeInTheDocument();
    expect(within(youth).queryByRole('article')).toBeNull();
    expect(stage('Childhood')).toHaveAttribute('data-open', 'true');
    expect(stage('Before the Glimpse')).toHaveAttribute('data-open', 'true');
    expect(section('Known for')).toHaveAttribute('data-open', 'false');
    // Opening the stage again brings its section back as it was left: open.
    await user.click(screen.getByRole('button', { name: /^Youth/ }));
    expect(stage('Youth')).toHaveAttribute('data-open', 'true');
    expect(section('Influences')).toHaveAttribute('data-open', 'true');
    // And the folded section opens again on its own line.
    await user.click(screen.getByTestId('sec-3'));
    expect(section('Known for')).toHaveAttribute('data-open', 'true');
    // Every fold can be shut at once.
    for (const name of ['Childhood', 'Youth', 'Before the Glimpse'])
      await user.click(screen.getByRole('button', { name: new RegExp(`^${name}`) }));
    expect(screen.queryAllByRole('article')).toHaveLength(0);
  });

  it('a closed section reads its answers with their signed points', async () => {
    const user = userEvent.setup();
    draftDistinctions = [picked(101, 11), picked(300, 30)];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    expect(within(stage('Childhood')).getByText('1 of 1')).toBeInTheDocument();
    // Its own line folds Known for to its answer and points; What marked it stays open
    // under it.
    await user.click(screen.getByTestId('sec-3'));
    const known = section('Known for');
    expect(known).toHaveAttribute('data-open', 'false');
    expect(within(known).getByText('Spied for a house')).toHaveClass('ans');
    expect(within(known).getByText('\u221210')).toHaveClass('cost');
    expect(section('What marked it')).toHaveAttribute('data-open', 'true');
    // No other fold moved.
    expect(section('Early Upbringing')).toHaveAttribute('data-open', 'true');
    expect(stage('Childhood')).toHaveAttribute('data-open', 'true');
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
    draftDistinctions = [picked(300, 30), picked(301, 31)];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const known = section('Known for');
    expect(within(known).getByRole('button', { name: /^Kept a shop/ })).toBeDisabled();
    expect(within(known).getByRole('button', { name: /^Spied for a house/ })).toBeEnabled();
  });

  it('a section that spends career points says its allowance once, in its own prompt (#5331)', () => {
    pool = [
      beat({
        beat_id: 5,
        name: 'Past Careers',
        prompt: '1 point for careers at age 19 and every 5 years after that.',
        life_stage: 'adulthood',
        selection: 'any',
        allowance: 1,
        allowance_is_points: true,
        answer_offer_ids: [30],
      }),
    ];
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const careers = section('Past Careers');
    expect(
      within(careers).getByText('1 point for careers at age 19 and every 5 years after that.')
    ).toBeInTheDocument();
    expect(within(careers).queryByText(/career points/)).toBeNull();
  });

  it('answers with a group read under headings with counts, the ungrouped last', async () => {
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const known = section('Known for');
    const groups = known.querySelectorAll('.offer-group');
    expect(groups).toHaveLength(2);
    expect(within(groups[0] as HTMLElement).getByText('Treatment (2)')).toHaveClass('group-h');
    expect(within(groups[0] as HTMLElement).getByRole('button', { name: /^Killed for coin/ }));
    expect(groups[1].querySelector('.group-h')).toBeNull();
    expect(within(groups[1] as HTMLElement).getByRole('button', { name: /^Kept a shop/ }));
  });

  it('a grid card wears a signed price, a free card none, and a term shows its definition on hover (#5148)', async () => {
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
    const term = within(patient).getByRole('button', { name: 'sailing, definition' });
    // Pointing at the term shows its definition; moving off hides it.
    await user.hover(term);
    expect(screen.getByRole('dialog', { name: 'sailing' })).toHaveTextContent(
      'Handling a ship at sea.'
    );
    await user.unhover(term);
    expect(screen.queryByRole('dialog')).toBeNull();
    // A click pins it open: it stays when the pointer leaves, and goes on Escape.
    await user.click(term);
    await user.unhover(term);
    expect(screen.getByRole('dialog', { name: 'sailing' })).toBeInTheDocument();
    // The term click is not a pick.
    expect(syncMutate).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).toBeNull();
    // A second click on a pinned term closes it.
    await user.click(term);
    expect(screen.getByRole('dialog', { name: 'sailing' })).toBeInTheDocument();
    await user.click(term);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('a term shows its definition while the keyboard focus is on it', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const patient = within(section('Early Upbringing')).getByRole('button', { name: /^Patient/ });
    const term = within(patient).getByRole('button', { name: 'sailing, definition' });
    act(() => term.focus());
    expect(screen.getByRole('dialog', { name: 'sailing' })).toBeInTheDocument();
    await user.tab();
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('a term nobody has written a definition for is plain text, not a promise of one', () => {
    offersResponse = {
      ...offersResponse,
      offers: offersResponse.offers.map((o) =>
        o.offer_id === 10
          ? {
              ...o,
              effects: [
                { target: 'sailing', label: 'sailing', value: 10, immune: false },
                { target: 'poise', label: 'poise', value: 5, immune: false },
                { target: 'menace', label: 'menace', value: -5, immune: false },
              ],
            }
          : o
      ),
      terms: [
        { name: 'sailing', label: 'sailing', definition: 'Handling a ship at sea.' },
        { name: 'poise', label: 'poise', definition: '  ' },
      ],
    };
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const patient = within(section('Early Upbringing')).getByRole('button', { name: /^Patient/ });
    const line = patient.querySelector('.fx')!;
    expect(line.textContent).toBe('+10 sailing; +5 poise; −5 menace');
    expect(Array.from(line.querySelectorAll('.term')).map((el) => el.textContent)).toEqual([
      'sailing',
    ]);
  });

  it("a grid card reads its distinction's description, not the offer's line (#5099)", () => {
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const patient = within(section('Early Upbringing')).getByRole('button', { name: /^Patient/ });
    expect(within(patient).getByText('You learned to wait out every storm.')).toBeInTheDocument();
    // The name prints once, as the card's title; the repeated player_line never shows.
    expect(within(patient).getAllByText('Patient')).toHaveLength(1);
  });

  it('every grid ends on an Amnesiac card that marks its own section unknown (#5102)', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft();
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const early = section('Early Upbringing');
    // No stage-wide mark any more; the card is the last one in the section's grid.
    expect(screen.queryByRole('button', { name: /^Unknown:/ })).toBeNull();
    const cards = within(early).getAllByRole('listitem');
    const amnesiac = within(cards.at(-1)!).getByRole('button', { name: /^Amnesiac/ });
    expect(amnesiac).toHaveTextContent('No memory of it at all.');
    expect(amnesiac).toHaveAttribute('aria-pressed', 'false');
    await user.click(amnesiac);
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '1': { unknown: true } } } },
    });
  });

  it('an Amnesiac section shows the card alone, picked, and a click brings the cards back', async () => {
    const user = userEvent.setup();
    const draft = createMockDraft({ draft_data: { beats: { '1': { unknown: true } } } });
    pool = pool.map((b) => (b.beat_id === 1 ? { ...b, unknown: true } : b));
    // The server closes an unknown beat's answers.
    offersResponse = {
      ...offersResponse,
      offers: offersResponse.offers.filter((o) => o.opener_key !== 'beat:1'),
    };
    renderWithCharacterCreationProviders(
      <LifeGrids draft={draft} copy={{ life_amnesiac_text: 'Staff line.' }} />
    );
    const early = section('Early Upbringing');
    const amnesiac = within(early).getByRole('button', { name: /^Amnesiac/ });
    expect(amnesiac).toHaveAttribute('aria-pressed', 'true');
    expect(amnesiac).toHaveTextContent('Staff line.');
    expect(within(early).queryByRole('button', { name: /^Patient/ })).toBeNull();
    await user.click(amnesiac);
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '1': { unknown: false } } } },
    });
  });

  it('a stage whose every section is Amnesiac reads Unknown and still lists its sections', async () => {
    pool = pool.map((b) => (b.life_stage === 'adulthood' ? { ...b, unknown: true } : b));
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    const before = screen.getByRole('region', { name: 'Before the Glimpse' });
    expect(within(before).getByText('Unknown', { selector: '.prog' })).toBeInTheDocument();
    // The sections stay, so each Amnesiac card can be taken back.
    expect(within(before).getAllByRole('article')).toHaveLength(2);
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
      data: { draft_data: { beats: { '1': { secret_offer_ids: [10], cover_offer_id: 12 } } } },
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
    const name = within(section('Influences')).getByLabelText('Rival: their name');
    expect(name).toHaveAttribute('maxlength', '60');
    await user.type(name, 'Ser Gaston');
    await user.tab();
    expect(mutateAsync).toHaveBeenLastCalledWith({
      draftId: draft.id,
      data: { draft_data: { beats: { '2': { figures: { '20': 'Ser Gaston' } } } } },
    });
  });

  it('the page has no free-text box about the life: no stage notes and no Recent History (#5178)', () => {
    // A draft saved before the change still holds the retired texts; none is shown.
    const draft = createMockDraft({
      draft_data: {
        stage_descriptions: { youth: 'Wild years.' },
        recent_history: 'A debt in Umbros.',
      } as Record<string, unknown>,
    });
    renderWithCharacterCreationProviders(
      <LifeGrids
        draft={draft}
        copy={{
          life_stage_notes_label: 'Background Notes',
          life_recent_history_label: 'Recent History (Optional)',
        }}
      />
    );
    expect(screen.getAllByRole('region').length).toBeGreaterThan(0);
    expect(screen.queryByText('Background Notes')).toBeNull();
    expect(screen.queryByText(/Recent History/)).toBeNull();
    expect(screen.queryByDisplayValue('Wild years.')).toBeNull();
    expect(screen.queryByDisplayValue('A debt in Umbros.')).toBeNull();
    expect(document.querySelector('.life textarea')).toBeNull();
  });

  it('the choices list every pick under its stage and print no totals (#5148)', async () => {
    draftDistinctions = [picked(101, 11), picked(300, 30)];
    const draft = createMockDraft({
      cg_points_spent: -5,
      cg_points_remaining: 105,
      draft_data: { beats: { '3': { secret_offer_ids: [30] } } },
    });
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />);
    const ledger = screen.getByRole('region', { name: 'Life So Far' });
    expect(within(ledger).getByRole('heading', { name: 'Life So Far' })).toHaveClass('rail-label');
    // The points line is the panel's own, the same on every stage: no purse here.
    expect(ledger.querySelector('.tot')).toBeNull();
    expect(ledger).not.toHaveTextContent(/Starting|Remaining|Spent|Gained/);
    const rows = Array.from(ledger.querySelectorAll('.row')).map((el) => el.textContent);
    expect(rows).toEqual(['Spoiled+10', 'Spied for a house (secret)−10']);
    expect(Array.from(ledger.querySelectorAll('.st')).map((el) => el.textContent)).toEqual([
      'Childhood',
      'Before the Glimpse',
    ]);
  });

  it('the foot of the life holds no box: no count line and no paragraph of the picks (#5201)', () => {
    draftDistinctions = [picked(101, 11), picked(300, 30)];
    const { container } = renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft()} copy={{}} />
    );
    expect(container.querySelector('.life-foot')).toBeNull();
    expect(container.querySelector('.testament')).toBeNull();
    expect(screen.queryByText(/taken, \d+ of \d+ points spent/)).toBeNull();
    // The life ends on its last stage.
    expect(container.querySelector('.life')!.lastElementChild).toHaveClass('stage-acc');
  });

  it('while a save is in flight the choices read the picks being saved (#5141)', () => {
    // Held: Spoiled (the world pays 10) and Spied for a house (10). The draft's totals
    // were added up from that list, so they net to nothing spent.
    const held = [
      { ...picked(101, 11), distinction_id: 101, cost: -10 },
      { ...picked(300, 30), distinction_id: 300, cost: 10 },
    ];
    draftDistinctions = held;
    const draft = createMockDraft({
      cg_points_spent: 0,
      cg_points_remaining: 100,
      draft_data: { distinctions: held as unknown as DraftDistinctionEntry[] },
    });
    // The click: Patient (10) in place of Spoiled on the one-of row. No answer yet.
    pendingSync = [
      { id: 300, rank: 1, offer_id: 30, feature_trait: '', feature_marking: 0 },
      { id: 100, rank: 1, offer_id: 10, feature_trait: '', feature_marking: 0 },
    ];
    const queryClient = new QueryClient({ defaultOptions: { queries: { gcTime: Infinity } } });
    queryClient.setQueryData(
      characterCreationKeys.draftOffers(draft.id, 'backgrounds'),
      offersResponse
    );
    renderWithCharacterCreationProviders(<LifeGrids draft={draft} copy={{}} />, { queryClient });
    const ledger = screen.getByRole('region', { name: 'Life So Far' });
    const rows = Array.from(ledger.querySelectorAll('.row')).map((el) => el.textContent);
    expect(rows).toEqual(['Patient−10', 'Spied for a house−10']);
  });

  it("inside a chapter the choices stand in its right-hand panel, under the stage's selections (#5148)", async () => {
    const { container } = renderWithCharacterCreationProviders(
      <ChapterLeaf stage={Stage.LINEAGE} title="Lineage" railSlot aside={<p>selections</p>}>
        <LifeGrids draft={createMockDraft()} copy={{}} />
      </ChapterLeaf>
    );
    const panel = screen.getByRole('complementary', { name: /marginalia/i });
    const choices = await screen.findByRole('region', { name: 'Life So Far' });
    expect(panel).toContainElement(choices);
    expect(panel.firstElementChild).toHaveTextContent('selections');
    expect(container.querySelector('.leafwrap')).not.toContainElement(choices);
    expect(container.querySelectorAll('.ledger')).toHaveLength(1);
  });

  it('with nothing chosen the rail says so', () => {
    renderWithCharacterCreationProviders(<LifeGrids draft={createMockDraft()} copy={{}} />);
    expect(screen.getByText('Nothing chosen yet.')).toHaveClass('empty');
    expect(screen.queryByText('Nothing written yet.')).toBeNull();
  });

  it('a beginning that strikes every stage shows its text where the stages were, and nothing to fill in', () => {
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
    expect(document.querySelector('.life textarea')).toBeNull();
    expect(screen.queryByText(/Recent History/)).toBeNull();
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
    expect(screen.getByText('Every stage of this life is struck.')).toHaveClass('absent');
  });

  it('an empty pool on a beginning that keeps its stages shows nothing', () => {
    pool = [];
    const { container } = renderWithCharacterCreationProviders(
      <LifeGrids draft={createMockDraft({ selected_beginnings: mockBeginnings })} copy={{}} />
    );
    expect(container.querySelector('.life')).toBeNull();
    expect(screen.queryByText(/points spent$/)).toBeNull();
  });
});

describe('LifeGrids (the suggested life, #4865)', () => {
  beforeEach(() => {
    loadMutate.mockClear();
    pool = [beat({ beat_id: 1, name: 'The household' })];
    offersResponse = { offers: [offer({ offer_id: 10, name: 'Spoiled' })], terms: [] };
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

  it("the life carries no button to clear it: that is the stage's Restart door (#5146)", () => {
    renderWithCharacterCreationProviders(
      <LifeGrids
        draft={createMockDraft({
          selected_beginnings: mockBeginnings,
          draft_data: { life_loaded_for: mockBeginnings.id },
        })}
        copy={{ beats_start_blank: 'Start blank' }}
      />
    );
    expect(screen.queryByText(/start blank/i)).toBeNull();
  });
});
