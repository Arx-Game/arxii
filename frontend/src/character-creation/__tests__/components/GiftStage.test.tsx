/**
 * GiftStage Component Tests (#3630 folio)
 *
 * Covers the funnel-as-entries shell: step names/tags always render, later
 * steps stay gated (and their pickers unmounted) until the step before them
 * is done, and the motif field is present. The individual pickers
 * (TraditionPicker, GiftSelector, TechniqueSelector, AnimaCheckStep,
 * GlimpseSection) have their own test files.
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { GiftStage } from '../../components/GiftStage';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import type {
  CGCombatStyleOption,
  CharacterDraft,
  GlimpseTagOption,
  OffersResponse,
  Resonance,
} from '../../types';
import {
  createMockDraft,
  mockBeginnings,
  mockCGExplanations,
  mockPath,
  mockResonances,
  mockSelfTaughtTradition,
  mockTradition,
} from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';

let traditions = [mockTradition];
let draftDistinctions: DraftDistinctionEntry[] = [];
let glimpseOffers: OffersResponse = { offers: [], terms: [], glimpse_cards: [] };
let glimpseOffersFetching = false;
let glimpseTags: GlimpseTagOption[] = [];
let cgExplanations = mockCGExplanations;
// The Primal and outward cards the Resonance step offers: Flame is the only Primal one.
const strengthResonances: Resonance[] = [
  ...mockResonances,
  {
    id: 3,
    name: 'Mercy',
    affinity: 1,
    affinity_name: 'Celestial',
    description: 'Gentle with the fallen',
    codex_entry_id: null,
    color_hex: '#F2E9B8',
  },
];
let combatStyles: CGCombatStyleOption[] = [];
const updateDraftMutate = vi.fn();

vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: cgExplanations }),
  useResonances: () => ({ data: strengthResonances, isLoading: false }),
  useUpdateDraft: () => ({ mutate: updateDraftMutate, mutateAsync: vi.fn() }),
  useTraditions: () => ({ data: traditions, isLoading: false }),
  useSelectTradition: () => ({ mutate: vi.fn(), isPending: false }),
  useTraditionPerspectives: () => ({ data: [] }),
  useCGGifts: () => ({ data: [], isLoading: false }),
  useCGCombatStyles: () => ({ data: combatStyles }),
  useCGTechniqueOptions: () => ({ data: [], isLoading: false }),
  useGlimpseTags: () => ({ data: glimpseTags, isLoading: false }),
  useDraftOffers: () => ({
    data: glimpseOffers,
    isLoading: false,
    isFetching: glimpseOffersFetching,
  }),
  useSkills: () => ({ data: [] }),
  useStatDefinitions: () => ({ data: [] }),
  usePathSkillSuggestions: () => ({ data: [] }),
  useCGPointBudget: () => ({ data: { starting_points: 100 } }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate: vi.fn() }),
  usePendingSync: () => null,
}));

beforeEach(() => {
  traditions = [mockTradition];
  draftDistinctions = [];
  glimpseOffers = { offers: [], terms: [], glimpse_cards: [] };
  glimpseOffersFetching = false;
  glimpseTags = [];
  cgExplanations = mockCGExplanations;
  combatStyles = [];
  updateDraftMutate.mockReset();
  // jsdom has no canvas: the aura draws nothing, the step still renders.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
});

describe('GiftStage (folio)', () => {
  it('shows the five steps as entries, later steps gated until the earlier is done', () => {
    const draft = createMockDraft({ selected_path: mockPath, selected_tradition: null });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const steps = screen.getByRole('list', { name: 'Gift steps' });
    expect(steps).toBeInTheDocument();
    expect(screen.getByText('Step 1 of 5')).toBeInTheDocument();
    expect(screen.getByText('Choose a tradition first')).toBeInTheDocument();
    // A gated step's picker never mounts, so it never fires its queries.
    expect(screen.queryByRole('list', { name: 'Gifts' })).not.toBeInTheDocument();
  });

  it('offers the motif as a field', () => {
    const draft = createMockDraft({ selected_path: mockPath });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByLabelText(/motif/i)).toBeInTheDocument();
  });

  it("prints the tradition's state line on its entry", () => {
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: null,
    });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(
      screen.getByText(
        'Living masters. They will teach you, and they will ask what you do with it.'
      )
    ).toBeInTheDocument();
  });

  it('names the Gifts and affinities a tradition teaches well on its entry (#4659)', () => {
    const draft = createMockDraft({
      selected_path: mockPath,
      selected_tradition: null,
      selected_beginnings: mockBeginnings,
    });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const line = screen.getByText(
      (_, el) => el?.tagName === 'P' && (el.textContent ?? '').startsWith('Teaches well')
    );
    expect(line).toHaveTextContent('Teaches well · Gifts: Whispers of Shadow · Affinity: Abyssal');
    expect(screen.getByText('Whispers of Shadow', { selector: '.tag' })).toBeInTheDocument();
  });

  describe('the resonance step (#5231)', () => {
    const pickedDraft = (weights: { resonance_id: number; weight: number }[]) =>
      createMockDraft({
        selected_path: mockPath,
        selected_tradition: mockTradition,
        draft_data: {
          selected_gift_id: 1,
          selected_technique_ids: [1],
          gift_resonance_weights: weights,
        },
      });
    const resonanceStepRows = () =>
      Array.from(screen.getByRole('list', { name: 'Gift steps' }).children) as HTMLElement[];

    it('saves a second pick as the whole list, the feeling first', async () => {
      renderWithCharacterCreationProviders(
        <GiftStage
          draft={pickedDraft([{ resonance_id: 2, weight: 10 }])}
          onRegisterBeforeLeave={vi.fn()}
        />
      );
      await userEvent.click(screen.getByRole('button', { name: 'Helping them' }));
      // The side alone saves nothing: she picks the card herself.
      expect(JSON.stringify(updateDraftMutate.mock.calls)).not.toContain('gift_resonance_weights');
      await userEvent.click(screen.getByRole('button', { name: /Mercy/ }));
      expect(updateDraftMutate).toHaveBeenCalledWith({
        draftId: 1,
        data: {
          draft_data: {
            gift_resonance_weights: [
              { resonance_id: 2, weight: 7 },
              { resonance_id: 3, weight: 3 },
            ],
          },
        },
      });
    });

    it('reads as chosen, naming the feeling and then the second pick', () => {
      renderWithCharacterCreationProviders(
        <GiftStage
          draft={pickedDraft([
            { resonance_id: 2, weight: 7 },
            { resonance_id: 1, weight: 3 },
          ])}
          onRegisterBeforeLeave={vi.fn()}
        />
      );
      const steps = resonanceStepRows();
      expect(steps[3]).toHaveClass('chosen');
      expect(steps[3]).toHaveTextContent('Flame, Shadow');
      expect(steps[3]).toHaveTextContent('Your Resonance');
      expect(screen.getAllByText('Your Resonance')).toHaveLength(1);
      expect(steps[4]).not.toHaveClass('closed');
    });

    it('stays open after a pick completes it, and arrives folded when already complete', async () => {
      const complete = [{ resonance_id: 2, weight: 10 }];
      const { rerender } = renderWithCharacterCreationProviders(
        <GiftStage draft={pickedDraft([])} onRegisterBeforeLeave={vi.fn()} />
      );
      expect(resonanceStepRows()[3].querySelector('details')).toHaveAttribute('open');
      await userEvent.click(screen.getByRole('button', { name: /Flame/ }));
      // The save lands and one feeling alone completes the step.
      rerender(<GiftStage draft={pickedDraft(complete)} onRegisterBeforeLeave={vi.fn()} />);
      const steps = resonanceStepRows();
      expect(steps[3]).toHaveClass('chosen');
      expect(steps[3].querySelector('details')).toHaveAttribute('open');
      expect(screen.getByRole('button', { name: 'Helping them' })).toBeInTheDocument();
    });

    it('shows a step that arrives already complete folded', () => {
      renderWithCharacterCreationProviders(
        <GiftStage
          draft={pickedDraft([{ resonance_id: 2, weight: 10 }])}
          onRegisterBeforeLeave={vi.fn()}
        />
      );
      const steps = resonanceStepRows();
      expect(steps[3]).toHaveClass('chosen');
      expect(steps[3].querySelector('details')).not.toHaveAttribute('open');
    });

    it('is not done for a draft saved under the old rule with three picks', () => {
      renderWithCharacterCreationProviders(
        <GiftStage
          draft={pickedDraft([
            { resonance_id: 2, weight: 5 },
            { resonance_id: 1, weight: 3 },
            { resonance_id: 3, weight: 2 },
          ])}
          onRegisterBeforeLeave={vi.fn()}
        />
      );
      const steps = resonanceStepRows();
      expect(steps[3]).not.toHaveClass('chosen');
      expect(steps[3].querySelector('details')).toHaveAttribute('open');
      expect(steps[4]).toHaveClass('closed');
      expect(steps[4]).toHaveTextContent('Choose a resonance first');
      // What she sees is what she must redo: nothing in the step reads as chosen.
      expect(steps[3].querySelectorAll('[aria-pressed="true"]')).toHaveLength(0);
    });

    it('is not done for a partial spread, and shows it as chosen nowhere', () => {
      renderWithCharacterCreationProviders(
        <GiftStage
          draft={pickedDraft([{ resonance_id: 2, weight: 4 }])}
          onRegisterBeforeLeave={vi.fn()}
        />
      );
      const steps = resonanceStepRows();
      expect(steps[3]).not.toHaveClass('chosen');
      expect(steps[3].querySelectorAll('[aria-pressed="true"]')).toHaveLength(0);
      expect(steps[4]).toHaveClass('closed');
    });
  });

  describe('the magical training step (#4659)', () => {
    const trainedDraft = (
      allocated: number,
      { giftId = 1, resonanceId = 2 }: { giftId?: number | null; resonanceId?: number | null } = {}
    ) =>
      createMockDraft({
        selected_path: mockPath,
        selected_tradition: mockTradition,
        draft_data: {
          selected_gift_id: giftId,
          gift_resonance_weights:
            resonanceId == null ? [] : [{ resonance_id: resonanceId, weight: 10 }],
        },
        magic_training: {
          ...createMockDraft().magic_training,
          base_sources: [{ name: 'Tradition Training', rank: 1, points: 20, show_rank: true }],
          total: 20,
          required_spend: 20,
          step: 10,
          allocated,
          skills: [{ id: 3, name: 'Occult', value: allocated, max: 30 }],
        },
      });

    /** The funnel's own steps, in order (each a direct child of the Gift steps list). */
    const funnelSteps = () =>
      Array.from(screen.getByRole('list', { name: 'Gift steps' }).children) as HTMLElement[];

    it('is its own step after the Resonance, open while the pool is unspent', () => {
      renderWithCharacterCreationProviders(
        <GiftStage draft={trainedDraft(0)} onRegisterBeforeLeave={vi.fn()} />
      );
      const steps = funnelSteps();
      expect(steps).toHaveLength(6);
      // Its affinity bonus reads the resonance, so it comes after that step.
      expect(steps[3]).toHaveTextContent('Resonance');
      expect(steps[3]).not.toHaveTextContent('taught you');
      const training = steps[4];
      expect(training).toHaveTextContent('What The Whispering Path taught you');
      expect(training).toHaveTextContent('Step 5 of 6');
      expect(training.querySelector('details')).toHaveAttribute('open');
      // The Tradition step above it is closed once chosen; the block is not inside it.
      expect(steps[0].querySelector('details')).not.toHaveAttribute('open');
      expect(steps[0]).not.toHaveTextContent('taught you');
      expect(steps[5]).toHaveTextContent('Step 6 of 6');
      expect(steps[5]).toHaveTextContent('Anima Check');
      expect(screen.getByText(/Remaining/)).toHaveTextContent('Remaining 20');
    });

    it('closes and reads as chosen once the pool is spent exactly', () => {
      renderWithCharacterCreationProviders(
        <GiftStage draft={trainedDraft(20)} onRegisterBeforeLeave={vi.fn()} />
      );
      const training = funnelSteps()[4];
      expect(training.querySelector('details')).not.toHaveAttribute('open');
      expect(training).toHaveClass('chosen');
    });

    it('is gated until a resonance is chosen', () => {
      renderWithCharacterCreationProviders(
        <GiftStage draft={trainedDraft(0, { resonanceId: null })} onRegisterBeforeLeave={vi.fn()} />
      );
      const training = funnelSteps()[4];
      expect(training).toHaveClass('closed');
      expect(training).toHaveTextContent('Choose a resonance first');
      expect(training.querySelector('details')).not.toHaveAttribute('open');
      expect(screen.queryByText(/Remaining/)).not.toBeInTheDocument();
    });

    it('is gated until a Gift is chosen', () => {
      renderWithCharacterCreationProviders(
        <GiftStage draft={trainedDraft(0, { giftId: null })} onRegisterBeforeLeave={vi.fn()} />
      );
      const training = funnelSteps()[4];
      expect(training).toHaveClass('closed');
      expect(training).toHaveTextContent('Choose a gift first');
      expect(training.querySelector('details')).not.toHaveAttribute('open');
    });
  });

  describe('the fighting style step (#4921)', () => {
    const dance: CGCombatStyleOption = {
      id: 7,
      name: 'The Daring Dance',
      description: 'Never where the blow lands.',
      defense_style: 'evasion',
      defense_style_display: 'Evasion',
      armor_share_tenths: 3,
      hit_stat_name: 'agility',
      weapon_kinds: [
        { value: 'melee_one_hand', label: 'One-Handed Melee' },
        { value: 'thrown', label: 'Thrown' },
      ],
      armor_kinds: [{ value: 'light_armor', label: 'Light Armor' }],
    };
    const mask: CGCombatStyleOption = {
      ...dance,
      id: 8,
      name: 'The Iron Mask',
      description: '',
      defense_style: 'gear_soak',
      defense_style_display: 'Mitigation',
      armor_share_tenths: 10,
      hit_stat_name: null,
      weapon_kinds: [{ value: 'melee_two_hand', label: 'Two-Handed Melee' }],
      armor_kinds: [
        { value: 'medium_armor', label: 'Medium Armor' },
        { value: 'heavy_armor', label: 'Heavy Armor' },
      ],
    };
    const styledDraft = (styleId: number | null, allocated = 0) =>
      createMockDraft({
        selected_path: mockPath,
        selected_tradition: mockTradition,
        selected_combat_style: styleId,
        draft_data: {
          selected_gift_id: 1,
          gift_resonance_weights: [{ resonance_id: 2, weight: 10 }],
        },
        magic_training: {
          ...createMockDraft().magic_training,
          total: 20,
          required_spend: 20,
          step: 10,
          allocated,
          skills: [{ id: 3, name: 'The Daring Dance', value: allocated, max: 30 }],
        },
      });
    const funnelSteps = () =>
      Array.from(screen.getByRole('list', { name: 'Gift steps' }).children) as HTMLElement[];

    it("lists the Tradition's styles after the Resonance, with how each attacks and defends", () => {
      combatStyles = [dance, mask];
      renderWithCharacterCreationProviders(
        <GiftStage draft={styledDraft(null)} onRegisterBeforeLeave={vi.fn()} />
      );
      const steps = funnelSteps();
      expect(steps).toHaveLength(7);
      const step = steps[4];
      expect(step).toHaveTextContent('Fighting style');
      expect(step).toHaveTextContent('Step 5 of 7');
      expect(step.querySelector('details')).toHaveAttribute('open');
      const list = within(step).getByRole('list', { name: 'Fighting styles' });
      expect(list).toHaveTextContent('one-handed melee, thrown · hits with Agility');
      expect(list).toHaveTextContent('evasion · light armor, 3 of 10 counts');
      expect(list).toHaveTextContent('two-handed melee');
      expect(list).toHaveTextContent('mitigation · medium armor or heavy armor, all of it counts');
      expect(list).not.toHaveTextContent(/vow/i);
      // The training waits on the style, whose skill its list holds.
      expect(steps[5]).toHaveTextContent('Choose a style first');
      expect(steps[6]).toHaveTextContent('Step 7 of 7');
    });

    it('saves the chosen style', async () => {
      combatStyles = [dance, mask];
      renderWithCharacterCreationProviders(
        <GiftStage draft={styledDraft(null)} onRegisterBeforeLeave={vi.fn()} />
      );
      // The name row's Select mark (the foot door carries the same label).
      await userEvent.click(screen.getAllByRole('button', { name: 'Select The Iron Mask' })[0]);
      expect(updateDraftMutate).toHaveBeenCalledWith({
        draftId: 1,
        data: { selected_combat_style_id: 8 },
      });
    });

    it('reads as chosen and opens the training once a style is picked', () => {
      combatStyles = [dance, mask];
      renderWithCharacterCreationProviders(
        <GiftStage draft={styledDraft(7)} onRegisterBeforeLeave={vi.fn()} />
      );
      const steps = funnelSteps();
      expect(steps[4]).toHaveClass('chosen');
      expect(steps[4].querySelector('details')).not.toHaveAttribute('open');
      expect(steps[5]).not.toHaveClass('closed');
      expect(steps[5]).toHaveTextContent('The Daring Dance');
    });

    it('is absent for a Tradition that teaches no style', () => {
      renderWithCharacterCreationProviders(
        <GiftStage draft={styledDraft(null)} onRegisterBeforeLeave={vi.fn()} />
      );
      expect(screen.queryByText('Fighting style')).not.toBeInTheDocument();
      expect(funnelSteps()).toHaveLength(6);
    });
  });

  it('has no training step when the draft has no training', () => {
    const draft = createMockDraft({ selected_path: mockPath, selected_tradition: mockTradition });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.queryByText(/taught you/)).not.toBeInTheDocument();
    expect(screen.getByText('Step 1 of 5')).toBeInTheDocument();
  });

  it('mounts the schooling stances under a chosen living-masters tradition', () => {
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: mockTradition,
    });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText('Newly taken in')).toBeInTheDocument();
    expect(screen.getByText('Trained for years')).toBeInTheDocument();
    expect(screen.getByText('Raised within it')).toBeInTheDocument();
  });

  it('substitutes the {tradition} token in the schooling label, fallback and authored', () => {
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: mockTradition,
    });
    const { unmount } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText('How you came to The Whispering Path')).toBeInTheDocument();
    unmount();

    cgExplanations = {
      ...mockCGExplanations,
      gift_schooling_label: 'How you trained with {tradition}',
    };
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText('How you trained with The Whispering Path')).toBeInTheDocument();
  });

  it('prints the refund and mounts no schooling for a self-taught tradition', () => {
    traditions = [mockSelfTaughtTradition];
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: mockSelfTaughtTradition,
    });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText('Self-taught · slower to learn · Awards 75')).toBeInTheDocument();
    expect(screen.queryByText('Newly taken in')).not.toBeInTheDocument();
    expect(screen.queryByText(/How you came to/)).not.toBeInTheDocument();
  });

  it('mounts the label and two stances for a teachers-gone tradition (the server decides)', () => {
    const orphaned = {
      ...mockTradition,
      id: 3,
      name: 'The Last Lamp',
      state: 'teachers_gone' as const,
      schooling: mockTradition.schooling.slice(0, 2),
    };
    traditions = [orphaned];
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: orphaned,
    });
    renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByText('How you came to The Last Lamp')).toBeInTheDocument();
    expect(screen.getByText('Newly taken in')).toBeInTheDocument();
    expect(screen.getByText('Trained for years')).toBeInTheDocument();
    expect(screen.queryByText('Raised within it')).not.toBeInTheDocument();
  });

  it('rail shows the tradition name plainly with no schooling picked', () => {
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: mockTradition,
    });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.getByText('The Whispering Path')).toBeInTheDocument();
  });

  it('rail appends the schooling pick to the tradition name', () => {
    draftDistinctions = [
      {
        distinction_id: 77,
        distinction_name: 'Tradition Training',
        distinction_slug: 'tradition-training',
        category_slug: 'magic',
        rank: 1,
        cost: 1,
        notes: '',
        offer_ids: [201],
        sources: ['Trained for years'],
        arrivals: ['choice'],
      },
    ];
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: mockTradition,
    });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.getByText('The Whispering Path · Trained for years')).toBeInTheDocument();
  });

  it('rail has no "Techniques to pick" row beside "Techniques" (#5199)', () => {
    const draft = createMockDraft({
      selected_beginnings: mockBeginnings,
      selected_path: mockPath,
      selected_tradition: mockTradition,
      starting_technique_picks: 3,
    });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.queryByText('Techniques to pick')).not.toBeInTheDocument();
    expect(rail.getByText('Techniques')).toBeInTheDocument();
  });

  it('rail shows the CG points every stage shows: spent of spent plus remaining', () => {
    const draft = createMockDraft({
      selected_path: mockPath,
      cg_points_spent: 42,
      cg_points_remaining: 58,
    });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.getByText('CG points')).toBeInTheDocument();
    expect(rail.getByText('42 of 100 spent')).toBeInTheDocument();
  });

  describe('the Glimpse rows of the side panel (#5292)', () => {
    const answer = (
      id: number,
      axis: GlimpseTagOption['axis'],
      name: string,
      cardName?: string
    ): GlimpseTagOption => ({
      id,
      axis,
      name,
      slug: name.toLowerCase(),
      description: '',
      example: '',
      sort_order: id,
      stands_alone: false,
      offers: cardName
        ? [
            {
              offer_id: id * 10,
              distinction_id: id * 10,
              name: cardName,
              player_line: '',
              cost_per_rank: 20,
              max_rank: 1,
              effect_line: '+Anima',
            },
          ]
        : [],
    });
    const given = (axis: string, name: string, source: string) => ({
      offer_id: 1,
      distinction_id: 1,
      name,
      source,
      axis,
      effect_line: '',
    });
    const noCards = (): OffersResponse => ({ offers: [], terms: [], glimpse_cards: [] });

    function railRows(draftData: CharacterDraft['draft_data']) {
      const draft = createMockDraft({ selected_path: mockPath, draft_data: draftData });
      const { container } = renderWithCharacterCreationProviders(
        <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
      );
      const rows: Record<string, string> = {};
      for (const row of container.querySelectorAll('.record-rail .row')) {
        rows[row.querySelector('dt')!.textContent!] = row.querySelector('dd')!.textContent!;
      }
      return rows;
    }

    beforeEach(() => {
      glimpseTags = [
        answer(1, 'TRIGGER', 'Crisis', 'Crisisborn'),
        answer(2, 'REFLECTION', 'Radiant', 'Glimmering'),
        answer(3, 'TONE', 'Grief'),
        answer(4, 'WITNESS', 'Public'),
      ];
    });

    it('reads the card each answered part gave, with no price, and names the parts that gave none', () => {
      glimpseOffers = { ...noCards(), glimpse_cards: [given('TRIGGER', 'Crisisborn', 'Crisis')] };
      const rows = railRows({ glimpse_tag_ids: [1, 3, 4] });

      expect(rows['Trigger']).toBe('Crisisborn');
      expect(rows['The Reflection']).toBe('not yet chosen');
      expect(rows['Tone']).toBe('no card');
      expect(rows['Consequence']).toBe('not yet chosen');
      // A part that gives no card has no row.
      expect(rows).not.toHaveProperty('Witness & Secrecy');
    });

    it('after a blackout the two parts it took read "not asked" and the marking card is held', () => {
      glimpseOffers = {
        ...noCards(),
        glimpse_cards: [
          given('TRIGGER', 'Crisisborn', 'Crisis'),
          given('', 'Glimpse Mystery', 'Blacked out'),
        ],
      };
      const rows = railRows({ glimpse_tag_ids: [1, 2], glimpse_memory: 'blacked_out' });

      expect(rows['Trigger']).toBe('Crisisborn');
      expect(rows['The Reflection']).toBe('not asked');
      expect(rows['Tone']).toBe('not asked');
      expect(rows['Glimpse Mystery']).toBe('held');
    });

    it('with no memory no part is asked and the marking card is held', () => {
      glimpseOffers = {
        ...noCards(),
        glimpse_cards: [given('', 'Glimpse Mystery', 'No memory')],
      };
      const rows = railRows({ glimpse_tag_ids: [1], glimpse_memory: 'no_memory' });

      expect(rows['Trigger']).toBe('not asked');
      expect(rows['Glimpse Mystery']).toBe('held');
    });

    it('with the Glimpse left for later no part is asked and nothing is held', () => {
      const rows = railRows({ glimpse_tag_ids: [1], glimpse_memory: 'later' });

      expect(rows['Consequence']).toBe('not asked');
      expect(rows).not.toHaveProperty('Glimpse Mystery');
    });

    it('while the cards are fetched again, the card printed on the answer stands in', () => {
      glimpseOffersFetching = true;
      const rows = railRows({ glimpse_tag_ids: [2] });

      expect(rows['The Reflection']).toBe('Glimmering');
    });
  });
});
