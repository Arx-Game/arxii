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
import { vi } from 'vitest';
import { GiftStage } from '../../components/GiftStage';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import type { OffersResponse } from '../../types';
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
let glimpseOffers: OffersResponse = { offers: [], closed: [] };

vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useResonances: () => ({ data: mockResonances, isLoading: false }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
  useTraditions: () => ({ data: traditions, isLoading: false }),
  useSelectTradition: () => ({ mutate: vi.fn(), isPending: false }),
  useTraditionPerspectives: () => ({ data: [] }),
  useCGGifts: () => ({ data: [], isLoading: false }),
  useCGTechniqueOptions: () => ({ data: [], isLoading: false }),
  useGlimpseTags: () => ({ data: [], isLoading: false }),
  useDraftOffers: () => ({ data: glimpseOffers, isLoading: false }),
  useSkills: () => ({ data: [] }),
  useStatDefinitions: () => ({ data: [] }),
  usePathSkillSuggestions: () => ({ data: [] }),
  useCGPointBudget: () => ({ data: { starting_points: 100 } }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate: vi.fn() }),
}));

beforeEach(() => {
  traditions = [mockTradition];
  draftDistinctions = [];
  glimpseOffers = { offers: [], closed: [] };
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
    expect(screen.getByText('Self-taught · slower to learn · Refunds 75')).toBeInTheDocument();
    expect(screen.queryByText('Newly taken in')).not.toBeInTheDocument();
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

  it('rail shows techniques to pick once a tradition is chosen', () => {
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
    expect(rail.getByText('Techniques to pick')).toBeInTheDocument();
    expect(rail.getByText('3')).toBeInTheDocument();
  });

  it('rail shows CG points from the same source HeritageStage uses', () => {
    const draft = createMockDraft({ selected_path: mockPath, cg_points_spent: 42 });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.getByText('CG points')).toBeInTheDocument();
    expect(rail.getByText('42 of 100 spent')).toBeInTheDocument();
  });

  it('rail shows one row per Glimpse offer entry, ranked with its rank and spent total (#3675 fix round 1)', () => {
    glimpseOffers = {
      offers: [
        {
          offer_id: 301,
          distinction_id: 40,
          name: 'Magical Scar',
          player_line: 'A scar that answers magic. Deeper answers more.',
          chapter: 'glimpse',
          arrives_as: 'choice',
          opener_label: 'Mark',
          cost_per_rank: 5,
          max_rank: 3,
          is_locked: false,
          lock_reason: '',
        },
      ],
      closed: [],
    };
    draftDistinctions = [
      {
        distinction_id: 40,
        distinction_name: 'Magical Scar',
        distinction_slug: 'magical-scar',
        category_slug: 'magic',
        rank: 2,
        cost: 10,
        notes: '',
        offer_ids: [301],
        sources: ['The Glimpse'],
        arrivals: ['choice'],
      },
    ];
    const draft = createMockDraft({ selected_path: mockPath });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.getByText('Magical Scar · rank 2')).toBeInTheDocument();
    expect(rail.getByText('10')).toBeInTheDocument();
  });

  it('rail shows an unranked Glimpse offer entry as a refund, with no rank suffix', () => {
    glimpseOffers = {
      offers: [
        {
          offer_id: 302,
          distinction_id: 41,
          name: 'Impoverished',
          player_line: 'Whatever you had went with it.',
          chapter: 'glimpse',
          arrives_as: 'choice',
          opener_label: 'Loss',
          cost_per_rank: -25,
          max_rank: 1,
          is_locked: false,
          lock_reason: '',
        },
      ],
      closed: [],
    };
    draftDistinctions = [
      {
        distinction_id: 41,
        distinction_name: 'Impoverished',
        distinction_slug: 'impoverished',
        category_slug: 'magic',
        rank: 1,
        cost: -25,
        notes: '',
        offer_ids: [302],
        sources: ['The Glimpse'],
        arrivals: ['choice'],
      },
    ];
    const draft = createMockDraft({ selected_path: mockPath });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.getByText('Impoverished')).toBeInTheDocument();
    expect(rail.getByText('Refunds 25')).toBeInTheDocument();
  });

  it('rail shows no Glimpse rows when no draft entry carries a Glimpse offer id', () => {
    draftDistinctions = [
      {
        distinction_id: 77,
        distinction_name: 'Tradition Training',
        distinction_slug: 'tradition-training',
        category_slug: 'magic',
        rank: 1,
        cost: 1,
        notes: '',
        offer_ids: [999],
        sources: ['Trained for years'],
        arrivals: ['choice'],
      },
    ];
    const draft = createMockDraft({ selected_path: mockPath });
    const { container } = renderWithCharacterCreationProviders(
      <GiftStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const rail = within(container.querySelector('.record-rail')!);
    expect(rail.queryByText('Tradition Training')).not.toBeInTheDocument();
  });
});
