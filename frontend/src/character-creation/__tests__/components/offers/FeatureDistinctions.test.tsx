/**
 * FeatureDistinctions (#3739): the per-feature Appearance rows.
 *
 * One authored line offered on every feature, held once per feature. What the
 * tests below pin is the part that is easy to get wrong: the payload carries
 * the feature, so two features of one distinction are two picks; the axes are
 * hidden until the unlock is held; and dropping the unlock drops the axes
 * bought under it in the same write, rather than sending the server a payload
 * it would refuse.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { FeatureDistinctions } from '../../../components/offers/FeatureDistinctions';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import type { OffersResponse } from '../../../types';
import { createMockDraft, makeVisibleOffer } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import { unreachableClasses } from './classGuard';

const mutate = vi.fn();

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));

vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate, isPending: false, isError: false }),
}));

const unlockOffer = makeVisibleOffer({
  offer_id: 900,
  distinction_id: 90,
  name: 'Make it distinctive',
  chapter: 'appearance',
  opener_key: 'feature',
  cost_per_rank: 1,
  max_rank: 1,
  taken_per_feature: true,
  opens_feature: true,
});

const alluringOffer = makeVisibleOffer({
  offer_id: 901,
  distinction_id: 91,
  name: 'Alluring',
  chapter: 'appearance',
  opener_key: 'feature',
  cost_per_rank: 2,
  max_rank: 5,
  cg_max_rank: 3,
  taken_per_feature: true,
  requires_feature_opened: true,
});

let offersResponse: OffersResponse = {
  offers: [unlockOffer, alluringOffer],
  closed: [],
};
let draftDistinctions: DraftDistinctionEntry[] = [];

function entry(
  distinctionId: number,
  offerId: number,
  rank: number,
  feature: { feature_trait?: string; feature_marking?: number }
): DraftDistinctionEntry {
  return {
    distinction_id: distinctionId,
    distinction_name: 'x',
    distinction_slug: 'x',
    category_slug: 'physical',
    rank,
    cost: rank,
    notes: '',
    offer_ids: [offerId],
    sources: [''],
    arrivals: ['choice'],
    feature_trait: feature.feature_trait ?? '',
    feature_marking: feature.feature_marking ?? 0,
  };
}

function renderBlock(feature: { feature_trait?: string; feature_marking?: number }) {
  return renderWithCharacterCreationProviders(
    <div className="interview">
      <FeatureDistinctions draft={createMockDraft()} feature={feature} featureLabel="Eye Colour" />
    </div>
  );
}

beforeEach(() => {
  mutate.mockClear();
  draftDistinctions = [];
  offersResponse = { offers: [unlockOffer, alluringOffer], closed: [] };
});

describe('FeatureDistinctions', () => {
  it('offers the unlock and hides the axes until it is held', () => {
    renderBlock({ feature_trait: 'eye_color' });
    expect(screen.getByRole('button', { name: /make it distinctive/i })).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: /Alluring on Eye Colour/ })).toBeNull();
  });

  it('shows the axes once the feature is distinctive', () => {
    draftDistinctions = [entry(90, 900, 1, { feature_trait: 'eye_color' })];
    renderBlock({ feature_trait: 'eye_color' });
    expect(screen.getByRole('group', { name: 'Alluring on Eye Colour' })).toBeInTheDocument();
  });

  it('sends the feature with the unlock', async () => {
    const user = userEvent.setup();
    renderBlock({ feature_trait: 'eye_color' });
    await user.click(screen.getByRole('button', { name: /make it distinctive/i }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 90, rank: 1, offer_id: 900, feature_trait: 'eye_color', feature_marking: 0 },
    ]);
  });

  it('sends a marking id when the feature is a marking', async () => {
    const user = userEvent.setup();
    renderBlock({ feature_marking: 12 });
    await user.click(screen.getByRole('button', { name: /make it distinctive/i }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 90, rank: 1, offer_id: 900, feature_trait: '', feature_marking: 12 },
    ]);
  });

  it('keeps another feature’s hold of the same distinction', async () => {
    const user = userEvent.setup();
    draftDistinctions = [entry(90, 900, 1, { feature_trait: 'hair_color' })];
    renderBlock({ feature_trait: 'eye_color' });
    await user.click(screen.getByRole('button', { name: /make it distinctive/i }));
    const sent = mutate.mock.calls[0][0];
    expect(sent).toHaveLength(2);
    expect(sent.map((row: { feature_trait: string }) => row.feature_trait).sort()).toEqual([
      'eye_color',
      'hair_color',
    ]);
  });

  it('raises an axis on this feature only', async () => {
    const user = userEvent.setup();
    draftDistinctions = [entry(90, 900, 1, { feature_trait: 'eye_color' })];
    renderBlock({ feature_trait: 'eye_color' });
    await user.click(screen.getByRole('button', { name: 'Raise Alluring on Eye Colour' }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 90, rank: 1, offer_id: 900, feature_trait: 'eye_color', feature_marking: 0 },
      { id: 91, rank: 1, offer_id: 901, feature_trait: 'eye_color', feature_marking: 0 },
    ]);
  });

  it('stops the axis at the character-creation ceiling', async () => {
    draftDistinctions = [
      entry(90, 900, 1, { feature_trait: 'eye_color' }),
      entry(91, 901, 3, { feature_trait: 'eye_color' }),
    ];
    renderBlock({ feature_trait: 'eye_color' });
    // cg_max_rank is 3 even though the distinction reaches 5 in play.
    expect(screen.getByRole('button', { name: 'Raise Alluring on Eye Colour' })).toBeDisabled();
  });

  it('drops the axes with the unlock that paid for them', async () => {
    const user = userEvent.setup();
    draftDistinctions = [
      entry(90, 900, 1, { feature_trait: 'eye_color' }),
      entry(91, 901, 2, { feature_trait: 'eye_color' }),
      entry(90, 900, 1, { feature_trait: 'hair_color' }),
    ];
    renderBlock({ feature_trait: 'eye_color' });
    await user.click(screen.getByRole('button', { name: /make it distinctive/i }));
    expect(mutate).toHaveBeenCalledWith([
      { id: 90, rank: 1, offer_id: 900, feature_trait: 'hair_color', feature_marking: 0 },
    ]);
  });

  it('renders nothing when no unlock is offered', () => {
    offersResponse = { offers: [alluringOffer], closed: [] };
    const { container } = renderBlock({ feature_trait: 'eye_color' });
    expect(container.querySelector('.feature-buy')).toBeNull();
  });

  it('every class hook it emits reaches a cg.css rule', () => {
    draftDistinctions = [entry(90, 900, 1, { feature_trait: 'eye_color' })];
    const { container } = renderBlock({ feature_trait: 'eye_color' });
    expect(unreachableClasses(container)).toEqual([]);
  });
});
