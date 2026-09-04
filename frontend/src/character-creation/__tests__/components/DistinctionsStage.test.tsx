import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { DistinctionsStage } from '../../components/DistinctionsStage';
import { createMockDraft, mockCGExplanations } from '../fixtures';
import { renderWithCharacterCreationProviders } from '../testUtils';

const categories = [
  { id: 1, name: 'Background', slug: 'background', description: '', display_order: 1 },
  { id: 2, name: 'Flaw', slug: 'flaw', description: '', display_order: 2 },
];
const distinctions = [
  {
    id: 10,
    name: 'Noble Blood',
    slug: 'noble-blood',
    description: 'Born to a house.',
    category_slug: 'background',
    cost_per_rank: 5,
    max_rank: 3,
    is_variant_parent: false,
    allow_other: false,
    tags: [],
    effects_summary: [{ text: '+1 Presence' }],
    is_locked: false,
    lock_reason: null,
    codex_entry_ids: [],
  },
  {
    id: 11,
    name: 'Hunted',
    slug: 'hunted',
    description: 'Someone wants you.',
    category_slug: 'flaw',
    cost_per_rank: -3,
    max_rank: 2,
    is_variant_parent: false,
    allow_other: false,
    tags: [],
    effects_summary: [],
    is_locked: true,
    lock_reason: 'Requires a Beginnings that allows it',
    codex_entry_ids: [],
  },
];

vi.mock('@/hooks/useDistinctions', () => ({
  useDistinctionCategories: () => ({ data: categories, isLoading: false }),
  useDistinctions: (params?: { category?: string }) => ({
    // The real hook filters server-side on the `category` param; "All" sends
    // none, which is the behaviour under test here.
    data: params?.category
      ? distinctions.filter((d) => d.category_slug === params.category)
      : distinctions,
    isLoading: false,
  }),
  useDraftDistinctions: () => ({
    data: [{ distinction_id: 10, distinction_slug: 'noble-blood', rank: 1, notes: '' }],
    isLoading: false,
  }),
  useSyncDistinctions: () => ({ mutateAsync: vi.fn().mockResolvedValue(undefined) }),
}));
vi.mock('../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../queries')>()),
  useCGPointBudget: () => ({
    data: { id: 1, name: 'b', starting_points: 120, xp_conversion_rate: 1, is_active: true },
  }),
  useCGExplanations: () => ({ data: mockCGExplanations }),
  useUpdateDraft: () => ({ mutate: vi.fn(), mutateAsync: vi.fn() }),
}));

describe('DistinctionsStage (folio)', () => {
  const draft = createMockDraft({ cg_points_spent: 5, cg_points_remaining: 115 });

  it('renders distinctions as stat rows with the purse at the head', () => {
    renderWithCharacterCreationProviders(
      <DistinctionsStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    expect(screen.getByRole('group', { name: 'Category' })).toBeInTheDocument();
    expect(screen.getByText(/Points remaining/)).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Raise Noble Blood' })).toBeEnabled();
  });

  it('keeps a locked distinction readable but not raisable, with the reason as the title', () => {
    renderWithCharacterCreationProviders(
      <DistinctionsStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const raise = screen.getByRole('button', { name: 'Raise Hunted' });
    expect(raise).toBeDisabled();
    expect(raise).toHaveAttribute('title', 'Requires a Beginnings that allows it');
    // The reason is visible on the row, not only in the button's title.
    expect(
      screen.getByText('-3 per rank · Requires a Beginnings that allows it')
    ).toBeInTheDocument();
  });

  it('opens on All with a group per category, and narrows to one when a category is chosen', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <DistinctionsStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    const groupTitles = () =>
      Array.from(document.querySelectorAll('.instr-group-h')).map((el) => el.textContent?.trim());

    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'true');
    expect(groupTitles()).toEqual(['Background', 'Flaw']);

    await user.click(screen.getByRole('button', { name: 'Flaw' }));

    expect(groupTitles()).toEqual(['Flaw']);
    expect(screen.queryByRole('button', { name: 'Raise Noble Blood' })).not.toBeInTheDocument();
  });

  it('writes what a distinction does into the margin when its name is pressed', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <DistinctionsStage draft={draft} onRegisterBeforeLeave={vi.fn()} />
    );
    await user.click(screen.getByRole('button', { name: 'Noble Blood' }));
    // Two role="status" nodes exist (the ChapterLeaf announcer and this note),
    // both with an empty accessible name, so getByRole('status', { name: '' })
    // is ambiguous here; the brief allows targeting the margin note directly.
    const note = document.getElementById('why-note');
    if (!note) throw new Error('expected #why-note to be rendered');
    expect(within(note).getByText(/Born to a house/)).toBeInTheDocument();
    expect(within(note).getByText(/\+1 Presence/)).toBeInTheDocument();
  });
});
