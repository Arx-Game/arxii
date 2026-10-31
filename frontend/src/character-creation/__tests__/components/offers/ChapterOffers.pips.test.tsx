/**
 * Career-point pips on a grid of ranked cards (#4829, slice 3 of #4813).
 *
 * A block that spends career points (`pointsPicks`) shows a ranked card's ranks as pips
 * in its top right: filled to the held rank, dimmed past the points the block has left,
 * and a click on a pip sets that rank (the held rank's own pip clears the card).
 */

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { ChapterOffers } from '../../../components/offers/ChapterOffers';
import { createMockDraft } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import type { OffersResponse, VisibleOffer } from '../../../types';
import type { DraftDistinctionEntry } from '@/types/distinctions';

const syncMutate = vi.fn();
let draftDistinctions: DraftDistinctionEntry[] = [];

function career(offerId: number, distinctionId: number, name: string): VisibleOffer {
  return {
    offer_id: offerId,
    distinction_id: distinctionId,
    name,
    distinction_name: name,
    player_line: `${name}, in your past.`,
    cost_per_rank: 0,
    max_rank: 4,
    is_locked: false,
    lock_reason: '',
    opener_key: 'beat:7',
    opener_label: 'Past Careers',
    held: false,
    first_look: false,
    effect_line: '',
    cg_max_rank: 0,
  } as unknown as VisibleOffer;
}

const offersResponse: OffersResponse = {
  offers: [career(401, 41, 'Sailor'), career(402, 42, 'Soldier')],
  closed: [],
} as unknown as OffersResponse;

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));
vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate: syncMutate, isPending: false }),
}));

function entry(distinctionId: number, offerId: number, rank: number): DraftDistinctionEntry {
  return {
    distinction_id: distinctionId,
    distinction_name: distinctionId === 41 ? 'Sailor' : 'Soldier',
    distinction_slug: '',
    category_slug: 'background',
    rank,
    cost: 0,
    notes: '',
    offer_ids: [offerId],
    sources: ['Past Careers'],
    arrivals: ['choice'],
    feature_trait: '',
    feature_marking: 0,
  } as DraftDistinctionEntry;
}

function renderGrid(maxPicks: number) {
  return renderWithCharacterCreationProviders(
    <ChapterOffers
      draft={createMockDraft({ id: 1 })}
      chapter="backgrounds"
      layout="grid"
      firstLook={false}
      showClosed={false}
      maxPicks={maxPicks}
      pointsPicks
    />
  );
}

describe('career-point pips', () => {
  beforeEach(() => {
    syncMutate.mockClear();
    draftDistinctions = [];
  });

  it('shows four pips on a ranked card, none filled before a pick', () => {
    renderGrid(7);
    const sailor = screen.getByRole('group', { name: 'Sailor' });
    const pips = within(sailor).getAllByRole('button', { name: /Sailor, rank \d/ });
    expect(pips).toHaveLength(4);
    expect(pips.every((pip) => pip.getAttribute('aria-pressed') === 'false')).toBe(true);
    expect(within(sailor).queryByLabelText('Raise Sailor')).toBeNull();
  });

  it('a click on a pip asks for that rank, and the held pip clears the card', async () => {
    const user = userEvent.setup();
    draftDistinctions = [entry(41, 401, 2)];
    renderGrid(7);
    const sailor = screen.getByRole('group', { name: 'Sailor' });
    await user.click(within(sailor).getByRole('button', { name: 'Sailor, rank 4' }));
    expect(syncMutate).toHaveBeenLastCalledWith([
      { id: 41, rank: 4, offer_id: 401, feature_trait: '', feature_marking: 0 },
    ]);
    await user.click(within(sailor).getByRole('button', { name: 'Sailor, rank 2' }));
    expect(syncMutate).toHaveBeenLastCalledWith([]);
  });

  it('dims the pips past the points the block has left', () => {
    // Seven points: Sailor at four and Soldier at three spend them all, so every
    // unfilled pip is past reach, while the filled ones stay clickable to lower.
    draftDistinctions = [entry(41, 401, 4), entry(42, 402, 3)];
    renderGrid(7);
    const soldier = screen.getByRole('group', { name: 'Soldier' });
    const fourth = within(soldier).getByRole('button', { name: 'Soldier, rank 4' });
    expect(fourth).toBeDisabled();
    expect(fourth.className).toContain('off');
    const third = within(soldier).getByRole('button', { name: 'Soldier, rank 3' });
    expect(third).toBeEnabled();
    expect(third.getAttribute('aria-pressed')).toBe('true');
  });

  it('counts ranks, not cards, toward the allowance', () => {
    // Two points: Sailor at two fills the block, so Soldier waits.
    draftDistinctions = [entry(41, 401, 2)];
    renderGrid(2);
    const soldier = screen.getByRole('group', { name: 'Soldier' });
    expect(soldier.getAttribute('aria-disabled')).toBe('true');
  });
});
