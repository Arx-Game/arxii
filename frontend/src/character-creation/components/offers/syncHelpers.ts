/**
 * Sync-payload helpers shared by `ChapterOffers` and `SchoolingStances`
 * (#3675): both write the draft's CHOICE distinctions through
 * `useSyncDistinctions`, and both need to resend every current CHOICE entry
 * unchanged alongside the one row they are actually changing, so a toggle in
 * one chapter's offers never drops another chapter's picks.
 */

import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';

/**
 * The CHOICE offer id an entry came from, if any.
 *
 * `offer_ids`/`arrivals` are index-aligned (the backend writes them in lockstep --
 * see `world.character_creation.offers` and `DistinctionsViewSet._build_sync_entries`),
 * so an entry is a choice entry only when its `arrivals` list actually contains
 * `'choice'` at some index; the id at that same index is the CHOICE offer. A
 * bundled-only or carried-only entry has an integer `offer_ids` entry too (a real
 * `DistinctionOffer` row), but no `'choice'` arrival, and must not be treated as one.
 * A legacy entry (drafts saved before the offers system, #3675) has no `arrivals`
 * key at all -- also not a choice entry, nothing to resend.
 */
export function choiceOfferId(entry: DraftDistinctionEntry): number | undefined {
  const index = (entry.arrivals ?? []).indexOf('choice');
  if (index === -1) return undefined;
  const offerId = entry.offer_ids?.[index];
  return typeof offerId === 'number' ? offerId : undefined;
}

/**
 * Every current CHOICE entry as a sync payload row. Carried entries (no
 * integer offer id) and bundled entries are dropped, the server re-applies
 * those on its own (`reconcile_offer_picks`).
 */
export function choiceEntries(
  entries: DraftDistinctionEntry[] | undefined
): SyncDistinctionEntry[] {
  const result: SyncDistinctionEntry[] = [];
  for (const entry of entries ?? []) {
    const offerId = choiceOfferId(entry);
    if (offerId === undefined) continue;
    result.push({
      id: entry.distinction_id,
      rank: entry.rank,
      offer_id: offerId,
      // #3739: the feature travels with the row, so resending another block's
      // picks never strips "Alluring on your scar" down to a plain "Alluring".
      feature_trait: entry.feature_trait ?? '',
      feature_marking: entry.feature_marking ?? 0,
    });
  }
  return result;
}

/**
 * The feature a row is aimed at, normalized (#3739): `['', 0]` for every
 * distinction that is not taken per feature. Used to tell two rows of one
 * distinction apart, in the same shape the server's `feature_key` uses.
 */
export type FeatureRef = { feature_trait?: string; feature_marking?: number };

export function featureKey(ref: FeatureRef): [string, number] {
  return [ref.feature_trait ?? '', ref.feature_marking ?? 0];
}

/** Whether two rows name the same feature. */
export function sameFeature(a: FeatureRef, b: FeatureRef): boolean {
  const [at, am] = featureKey(a);
  const [bt, bm] = featureKey(b);
  return at === bt && am === bm;
}
