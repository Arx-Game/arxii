/**
 * ChapterOffers Component Tests (#3675).
 *
 * The reusable offers block every CG chapter mounts in place of the retired
 * Distinctions stage: renders a chapter's visible offers as folio stances,
 * writes selection through `useSyncDistinctions` immediately, and prints the
 * closed list with its reason.
 */

/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ChapterOffers } from '../../../components/offers/ChapterOffers';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import type { OffersResponse, VisibleOffer } from '../../../types';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';

const mutate = vi.fn();

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));

vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate }),
}));

const silverTongue: VisibleOffer = {
  offer_id: 101,
  distinction_id: 1,
  name: 'Silver Tongue',
  player_line: 'You always know the right thing to say.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: 'Mark',
  cost_per_rank: -25,
  max_rank: 1,
  is_locked: false,
  lock_reason: '',
};

const magicalScar: VisibleOffer = {
  offer_id: 102,
  distinction_id: 2,
  name: 'Magical Scar',
  player_line: 'A scar that answers magic. Deeper answers more.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: '',
  cost_per_rank: 5,
  max_rank: 3,
  is_locked: false,
  lock_reason: '',
};

const highborn: VisibleOffer = {
  offer_id: 103,
  distinction_id: 3,
  name: 'Highborn',
  player_line: 'Blood runs true.',
  chapter: 'glimpse',
  arrives_as: 'choice',
  opener_label: 'Public',
  cost_per_rank: 20,
  max_rank: 1,
  is_locked: true,
  lock_reason: 'The Cradle raised this character; the route closed it.',
};

/** A CHOICE entry from a different chapter's offer, to prove a toggle never drops it. */
const otherChapterEntry: DraftDistinctionEntry = {
  distinction_id: 50,
  distinction_name: 'Leal Agent',
  distinction_slug: 'leal-agent',
  category_slug: 'social',
  rank: 2,
  cost: 10,
  notes: '',
  offer_ids: [999],
  sources: ['A house bought you out'],
  arrivals: ['choice'],
};

let offersResponse: OffersResponse;
let draftDistinctions: DraftDistinctionEntry[];

beforeEach(() => {
  mutate.mockClear();
  offersResponse = {
    offers: [silverTongue, magicalScar, highborn],
    closed: [{ distinction_id: 9, name: 'Generational Talent', reason: 'The route closed it.' }],
  };
  draftDistinctions = [otherChapterEntry];
});

describe('ChapterOffers', () => {
  it('renders offers with their price, opener label and refund/per-rank formats', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(screen.getByText('Silver Tongue')).toBeInTheDocument();
    expect(screen.getByText('You always know the right thing to say.')).toBeInTheDocument();
    expect(screen.getByText('From Mark.')).toBeInTheDocument();
    expect(screen.getByText('Refunds 25')).toBeInTheDocument();
    expect(screen.getByText('Magical Scar')).toBeInTheDocument();
    expect(screen.getByText('5 per rank')).toBeInTheDocument();
  });

  it('toggling an offer syncs every CHOICE entry, including the new offer_id', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    await user.click(screen.getByRole('button', { name: /Silver Tongue/ }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 50, rank: 2, offer_id: 999 },
      { id: 1, rank: 1, offer_id: 101 },
    ]);
  });

  it('a locked row is aria-disabled, shows its reason, and cannot be toggled', async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    const row = screen.getByRole('button', { name: /Highborn/ });
    expect(row).toHaveAttribute('aria-disabled', 'true');
    expect(row).toBeDisabled();
    expect(
      screen.getByText('The Cradle raised this character; the route closed it.')
    ).toBeInTheDocument();
    await user.click(row);
    expect(mutate).not.toHaveBeenCalled();
  });

  it("a ranked offer's control raises its rank and syncs the new entry", async () => {
    const user = userEvent.setup();
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    await user.click(screen.getByRole('button', { name: 'Raise Magical Scar' }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 50, rank: 2, offer_id: 999 },
      { id: 2, rank: 1, offer_id: 102 },
    ]);
  });

  it('renders the closed hint with the names and reason', () => {
    renderWithCharacterCreationProviders(
      <ChapterOffers draft={createMockDraft()} chapter="glimpse" />
    );
    expect(
      screen.getByText('Closed on this road: Generational Talent. The route closed it.')
    ).toBeInTheDocument();
  });

  it('emits no class hook that cg.css has no rule for (#3667 shape)', () => {
    const { container } = renderWithCharacterCreationProviders(
      <ChapterOffers
        draft={createMockDraft()}
        chapter="glimpse"
        heading="What it left in you"
        hint="staff copy"
      />
    );
    const css = readFileSync(resolve(__dirname, '../../../cg.css'), 'utf8');
    const emitted = new Set<string>();
    container.querySelectorAll('[class]').forEach((el) => {
      el.className
        .split(/\s+/)
        .filter(Boolean)
        .forEach((name) => emitted.add(name));
    });
    const styledElsewhere = new Set(['chosen', 'closed']);
    const unstyled = [...emitted].filter(
      (name) => !styledElsewhere.has(name) && !new RegExp(`\\.${name}(?![\\w-])`).test(css)
    );
    expect(unstyled).toEqual([]);
  });
});
