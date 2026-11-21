/**
 * FeatureDistinctions (#3739, #5241): a feature's qualities line.
 *
 * One authored line offered on every feature, held once per feature. What the
 * tests below pin is the part that is easy to get wrong: the qualities are on the
 * page with no step before them; the payload carries the feature, so two features
 * of one quality are two picks; a click shows from the save in flight and no
 * second click is taken until it answers; and the caller hears when the last tier
 * comes off a feature.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { FeatureDistinctions } from '../../../components/offers/FeatureDistinctions';
import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';
import type { OffersResponse } from '../../../types';
import { createMockDraft, makeVisibleOffer } from '../../fixtures';
import { renderWithCharacterCreationProviders } from '../../testUtils';
import { unreachableClasses } from './classGuard';

const mutate = vi.fn();
const onClosed = vi.fn();

vi.mock('../../../queries', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../queries')>()),
  useDraftOffers: () => ({ data: offersResponse, isLoading: false }),
}));

vi.mock('@/hooks/useDistinctions', () => ({
  useDraftDistinctions: () => ({ data: draftDistinctions }),
  useSyncDistinctions: () => ({ mutate, isPending: false, isError: false, pendingEntries }),
}));

const alluringOffer = makeVisibleOffer({
  offer_id: 901,
  distinction_id: 91,
  name: 'Alluring',
  player_line: 'The one people cannot look away from.',
  chapter: 'appearance',
  opener_key: 'feature',
  cost_per_rank: 1,
  max_rank: 5,
  cg_max_rank: 3,
  taken_per_feature: true,
});

const menacingOffer = makeVisibleOffer({
  offer_id: 902,
  distinction_id: 92,
  name: 'Menacing',
  chapter: 'appearance',
  opener_key: 'feature',
  cost_per_rank: 1,
  max_rank: 5,
  cg_max_rank: 3,
  taken_per_feature: true,
});

const sectionOffer = makeVisibleOffer({
  offer_id: 950,
  distinction_id: 95,
  name: 'Broad Shouldered',
  chapter: 'appearance',
  opener_key: 'frame',
});

let offersResponse: OffersResponse = { offers: [], terms: [] };
let draftDistinctions: DraftDistinctionEntry[] = [];
let pendingEntries: SyncDistinctionEntry[] | null = null;

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
      <FeatureDistinctions
        draft={createMockDraft()}
        feature={feature}
        featureLabel="Eye Colour"
        onClosed={onClosed}
      />
    </div>
  );
}

const tier = (quality: string, n: number) =>
  screen.getByRole('button', { name: `${quality} on Eye Colour, tier ${n}` });

beforeEach(() => {
  mutate.mockClear();
  onClosed.mockClear();
  draftDistinctions = [];
  pendingEntries = null;
  offersResponse = { offers: [sectionOffer, alluringOffer, menacingOffer], terms: [] };
});

describe('FeatureDistinctions', () => {
  it('shows every quality on a feature that holds nothing, with no step before them', () => {
    renderBlock({ feature_trait: 'eye_color' });
    expect(screen.getByRole('list', { name: 'Qualities of Eye Colour' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Alluring on Eye Colour' })).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Menacing on Eye Colour' })).toBeInTheDocument();
    expect(screen.queryByText(/make it distinctive/i)).toBeNull();
    // A sectioned Appearance line is not a quality.
    expect(screen.queryByText('Broad Shouldered')).toBeNull();
  });

  it('stops a quality at the character-creation ceiling', () => {
    renderBlock({ feature_trait: 'eye_color' });
    // cg_max_rank is 3 even though the distinction reaches 5 in play.
    expect(screen.getAllByRole('button', { name: /^Alluring on Eye Colour, tier/ })).toHaveLength(
      3
    );
  });

  it('says what a quality is on hover', () => {
    renderBlock({ feature_trait: 'eye_color' });
    expect(screen.getByText('Alluring')).toHaveAttribute(
      'title',
      'The one people cannot look away from.'
    );
  });

  it('sets a tier with one click and sends the feature with it', async () => {
    const user = userEvent.setup();
    renderBlock({ feature_trait: 'eye_color' });
    await user.click(tier('Alluring', 2));
    expect(mutate).toHaveBeenCalledWith([
      { id: 91, rank: 2, offer_id: 901, feature_trait: 'eye_color', feature_marking: 0 },
    ]);
    expect(onClosed).not.toHaveBeenCalled();
  });

  it('sends a marking id when the feature is a marking', async () => {
    const user = userEvent.setup();
    renderBlock({ feature_marking: 12 });
    await user.click(tier('Menacing', 1));
    expect(mutate).toHaveBeenCalledWith([
      { id: 92, rank: 1, offer_id: 902, feature_trait: '', feature_marking: 12 },
    ]);
  });

  it('marks the tiers held and keeps another feature’s hold of the same quality', async () => {
    const user = userEvent.setup();
    draftDistinctions = [
      entry(91, 901, 2, { feature_trait: 'eye_color' }),
      entry(91, 901, 1, { feature_trait: 'hair_color' }),
    ];
    renderBlock({ feature_trait: 'eye_color' });
    expect(tier('Alluring', 1)).toHaveAttribute('aria-pressed', 'true');
    expect(tier('Alluring', 2)).toHaveAttribute('aria-pressed', 'true');
    expect(tier('Alluring', 3)).toHaveAttribute('aria-pressed', 'false');

    await user.click(tier('Alluring', 3));
    expect(mutate).toHaveBeenCalledWith([
      { id: 91, rank: 1, offer_id: 901, feature_trait: 'hair_color', feature_marking: 0 },
      { id: 91, rank: 3, offer_id: 901, feature_trait: 'eye_color', feature_marking: 0 },
    ]);
  });

  it('takes the top tier off when it is pressed again', async () => {
    const user = userEvent.setup();
    draftDistinctions = [
      entry(91, 901, 2, { feature_trait: 'eye_color' }),
      entry(92, 902, 1, { feature_trait: 'eye_color' }),
    ];
    renderBlock({ feature_trait: 'eye_color' });
    await user.click(tier('Alluring', 2));
    expect(mutate).toHaveBeenCalledWith([
      { id: 92, rank: 1, offer_id: 902, feature_trait: 'eye_color', feature_marking: 0 },
      { id: 91, rank: 1, offer_id: 901, feature_trait: 'eye_color', feature_marking: 0 },
    ]);
    // Menacing still holds a tier here, so the feature is still distinctive.
    expect(onClosed).not.toHaveBeenCalled();
  });

  it('tells the caller when the last tier comes off the feature', async () => {
    const user = userEvent.setup();
    draftDistinctions = [
      entry(91, 901, 1, { feature_trait: 'eye_color' }),
      entry(91, 901, 1, { feature_trait: 'hair_color' }),
    ];
    renderBlock({ feature_trait: 'eye_color' });
    await user.click(tier('Alluring', 1));
    expect(mutate).toHaveBeenCalledWith([
      { id: 91, rank: 1, offer_id: 901, feature_trait: 'hair_color', feature_marking: 0 },
    ]);
    expect(onClosed).toHaveBeenCalledTimes(1);
  });

  it('shows a click from the save in flight and takes no second click until it answers', () => {
    pendingEntries = [
      { id: 91, rank: 3, offer_id: 901, feature_trait: 'eye_color', feature_marking: 0 },
    ];
    renderBlock({ feature_trait: 'eye_color' });
    expect(tier('Alluring', 3)).toHaveAttribute('aria-pressed', 'true');
    expect(tier('Alluring', 3)).toBeDisabled();
    expect(tier('Menacing', 1)).toBeDisabled();
  });

  it('renders nothing when staff have authored no quality', () => {
    offersResponse = { offers: [sectionOffer], terms: [] };
    const { container } = renderBlock({ feature_trait: 'eye_color' });
    expect(container.querySelector('.qualities')).toBeNull();
  });

  it('every class hook it emits reaches a cg.css rule', () => {
    draftDistinctions = [entry(91, 901, 1, { feature_trait: 'eye_color' })];
    const { container } = renderBlock({ feature_trait: 'eye_color' });
    expect(unreachableClasses(container)).toEqual([]);
  });
});
