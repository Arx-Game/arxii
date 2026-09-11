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
import { choiceEntries, choiceOfferId } from '../../../components/offers/syncHelpers';

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
