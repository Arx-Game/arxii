/**
 * syncHelpers tests (#3675 final fix F1).
 *
 * `choiceOfferId`/`choiceEntries` must resend only entries whose `arrivals`
 * list actually contains `'choice'` -- a bundled-only or carried-only entry
 * still carries an integer `offer_ids` entry (a real `DistinctionOffer` row),
 * and treating that as a CHOICE pick resent it on every sync, which the
 * server rejected (400, no visible feedback).
 */

import { describe, expect, it } from 'vitest';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import {
  choiceEntries,
  choiceOfferId,
  picksCost,
  shownPicks,
} from '../../../components/offers/syncHelpers';

function entry(overrides: Partial<DraftDistinctionEntry>): DraftDistinctionEntry {
  return {
    distinction_id: 1,
    distinction_name: 'Test Distinction',
    distinction_slug: 'test-distinction',
    category_slug: 'social',
    rank: 1,
    cost: 5,
    notes: '',
    offer_ids: [],
    sources: [],
    arrivals: [],
    ...overrides,
  };
}

describe('choiceOfferId', () => {
  it('returns undefined for a bundled-only entry', () => {
    const e = entry({ offer_ids: [201], sources: ['A group question'], arrivals: ['bundled'] });
    expect(choiceOfferId(e)).toBeUndefined();
  });

  it('returns undefined for a carried-only entry', () => {
    const e = entry({
      offer_ids: ['state:self_taught'],
      sources: ['No one ever taught you.'],
      arrivals: ['carried'],
    });
    expect(choiceOfferId(e)).toBeUndefined();
  });

  it('returns the id at the matching index for a mixed choice + bundled entry', () => {
    const e = entry({
      offer_ids: [301, 302],
      sources: ['A group question', 'The player chose it'],
      arrivals: ['bundled', 'choice'],
    });
    expect(choiceOfferId(e)).toBe(302);
  });

  it('returns undefined for a legacy entry with no offer_ids/arrivals at all', () => {
    const legacy = {
      distinction_id: 1,
      distinction_name: 'Legacy Pick',
      distinction_slug: 'legacy-pick',
      category_slug: 'social',
      rank: 1,
      cost: 5,
      notes: '',
    } as unknown as DraftDistinctionEntry;
    expect(choiceOfferId(legacy)).toBeUndefined();
  });

  it('returns the id for a plain choice entry', () => {
    const e = entry({ offer_ids: [101], sources: ['The Glimpse'], arrivals: ['choice'] });
    expect(choiceOfferId(e)).toBe(101);
  });
});

describe('choiceEntries', () => {
  it('excludes a bundled-only entry', () => {
    const bundledOnly = entry({
      distinction_id: 2,
      offer_ids: [201],
      sources: ['A group question'],
      arrivals: ['bundled'],
    });
    expect(choiceEntries([bundledOnly])).toEqual([]);
  });

  it('excludes a carried-only entry', () => {
    const carriedOnly = entry({
      distinction_id: 3,
      offer_ids: ['state:self_taught'],
      sources: ['No one ever taught you.'],
      arrivals: ['carried'],
    });
    expect(choiceEntries([carriedOnly])).toEqual([]);
  });

  it('sends only the choice id from a mixed choice + bundled entry', () => {
    const mixed = entry({
      distinction_id: 4,
      rank: 2,
      offer_ids: [301, 302],
      sources: ['A group question', 'The player chose it'],
      arrivals: ['bundled', 'choice'],
    });
    expect(choiceEntries([mixed])).toEqual([
      { id: 4, rank: 2, offer_id: 302, feature_trait: '', feature_marking: 0 },
    ]);
  });

  it('excludes a legacy entry without offer_ids', () => {
    const legacy = {
      distinction_id: 5,
      distinction_name: 'Legacy Pick',
      distinction_slug: 'legacy-pick',
      category_slug: 'social',
      rank: 1,
      cost: 5,
      notes: '',
    } as unknown as DraftDistinctionEntry;
    expect(choiceEntries([legacy])).toEqual([]);
  });

  it('returns [] for undefined entries', () => {
    expect(choiceEntries(undefined)).toEqual([]);
  });
});

describe('shownPicks (#5141)', () => {
  const noOffer = () => undefined;
  const row = (id: number, offerId: number, rank = 1) => ({
    id,
    rank,
    offer_id: offerId,
    feature_trait: '',
    feature_marking: 0,
  });
  const chosen = entry({
    distinction_id: 1,
    rank: 1,
    cost: 5,
    offer_ids: [11],
    arrivals: ['choice'],
  });
  const bundled = entry({
    distinction_id: 2,
    rank: 1,
    cost: 0,
    offer_ids: [22],
    arrivals: ['bundled'],
  });

  it('with no save in flight it is the saved list at the prices the server charged', () => {
    const picks = shownPicks([chosen, bundled], null, noOffer);
    expect(picks.map((p) => [p.distinction_id, p.rank, p.cost])).toEqual([
      [1, 1, 5],
      [2, 1, 0],
    ]);
    expect(picksCost(picks)).toBe(5);
  });

  it('a pick the save adds is priced from its offer', () => {
    const picks = shownPicks([chosen], [row(1, 11), row(3, 33, 2)], (offerId) =>
      offerId === 33 ? -4 : undefined
    );
    expect(picks.map((p) => [p.distinction_id, p.offer_ids, p.rank, p.cost])).toEqual([
      [1, [11], 1, 5],
      [3, [33], 2, -8],
    ]);
  });

  it('a pick the save leaves out is let go, and one held another way stays', () => {
    const picks = shownPicks([chosen, bundled], [], noOffer);
    expect(picks.map((p) => p.distinction_id)).toEqual([2]);
    expect(picksCost(picks)).toBe(0);
  });

  it('a changed rank is re-priced from what the server charged per rank', () => {
    const ranked = entry({
      distinction_id: 4,
      rank: 2,
      cost: 6,
      offer_ids: [44],
      arrivals: ['choice'],
    });
    const picks = shownPicks([ranked], [row(4, 44, 3)], noOffer);
    expect(picks.map((p) => [p.rank, p.cost])).toEqual([[3, 9]]);
  });

  it('a chosen pick that another offer also grants keeps that offer when let go', () => {
    const both = entry({
      distinction_id: 5,
      rank: 1,
      cost: 0,
      offer_ids: [51, 52],
      arrivals: ['choice', 'bundled'],
    });
    const picks = shownPicks([both], [], noOffer);
    expect(picks.map((p) => [p.distinction_id, p.offer_ids, p.cost])).toEqual([[5, [52], 0]]);
  });

  it('choosing a distinction already held for nothing changes no price', () => {
    const picks = shownPicks([bundled], [row(2, 29)], () => 7);
    expect(picks.map((p) => [p.distinction_id, p.offer_ids, p.cost])).toEqual([[2, [22, 29], 0]]);
  });

  it('the same distinction on another feature is its own pick', () => {
    const scar = entry({
      distinction_id: 6,
      rank: 1,
      cost: 3,
      offer_ids: [61],
      arrivals: ['choice'],
      feature_trait: 'scar',
    });
    const picks = shownPicks(
      [scar],
      [
        { id: 6, rank: 1, offer_id: 61, feature_trait: 'scar', feature_marking: 0 },
        { id: 6, rank: 1, offer_id: 61, feature_trait: 'eyes', feature_marking: 0 },
      ],
      () => 3
    );
    expect(picks.map((p) => [p.feature_trait, p.cost])).toEqual([
      ['scar', 3],
      ['eyes', 3],
    ]);
  });
});
