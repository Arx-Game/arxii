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

/**
 * One held distinction as the page shows it (#5141): the offers it came from, its rank
 * and the points it costs (negative when the world pays).
 */
export interface ShownPick {
  distinction_id: number;
  offer_ids: (number | string)[];
  rank: number;
  cost: number;
  feature_trait: string;
  feature_marking: number;
}

function asShown(entry: DraftDistinctionEntry): ShownPick {
  const [feature_trait, feature_marking] = featureKey(entry);
  return {
    distinction_id: entry.distinction_id,
    offer_ids: entry.offer_ids ?? [],
    rank: entry.rank,
    cost: entry.cost ?? 0,
    feature_trait,
    feature_marking,
  };
}

/** The points a list of picks costs together. */
export function picksCost(picks: { cost?: number }[] | undefined): number {
  return (picks ?? []).reduce((sum, pick) => sum + (pick.cost ?? 0), 0);
}

/**
 * The picks to show (#5141): the saved list, with a save in flight laid over it.
 *
 * With no save in flight this is the saved list. With one, every chosen pick reads the
 * save's rows, because the save replaces all of them: a pick the save leaves out is let
 * go (it stays only when another offer still grants it), a pick whose rank the save
 * changes is re-priced from the price the server charged per rank, and a pick the draft
 * does not hold yet is priced from its offer (`costPerRank`). A pick the draft holds
 * some other way than by choice (bundled, carried) is not in a save and keeps its price.
 * The server's answer replaces all of this, so a price it works out differently shows
 * as soon as the save lands.
 */
export function shownPicks(
  saved: DraftDistinctionEntry[] | undefined,
  pending: SyncDistinctionEntry[] | null,
  costPerRank: (offerId: number) => number | undefined
): ShownPick[] {
  if (pending === null) return (saved ?? []).map(asShown);
  const used = new Set<number>();
  const shown: ShownPick[] = [];
  for (const entry of saved ?? []) {
    const pick = asShown(entry);
    const chosen = choiceOfferId(entry);
    if (chosen === undefined) {
      shown.push(pick);
      continue;
    }
    const at = pending.findIndex(
      (row, i) => !used.has(i) && row.offer_id === chosen && sameFeature(row, entry)
    );
    if (at === -1 || pending[at].rank <= 0) {
      if (at !== -1) used.add(at);
      const others = pick.offer_ids.filter((id) => id !== chosen);
      if (others.length > 0) shown.push({ ...pick, offer_ids: others });
      continue;
    }
    used.add(at);
    const rank = pending[at].rank;
    const perRank = entry.rank > 0 ? pick.cost / entry.rank : (costPerRank(chosen) ?? 0);
    shown.push({ ...pick, rank, cost: rank === entry.rank ? pick.cost : perRank * rank });
  }
  pending.forEach((row, i) => {
    if (used.has(i) || row.rank <= 0) return;
    const held = shown.find((pick) => pick.distinction_id === row.id && sameFeature(pick, row));
    if (held) {
      // Already held for nothing by another offer: choosing it as well changes no price.
      held.offer_ids = [...held.offer_ids, row.offer_id];
      return;
    }
    const [feature_trait, feature_marking] = featureKey(row);
    shown.push({
      distinction_id: row.id,
      offer_ids: [row.offer_id],
      rank: row.rank,
      cost: (costPerRank(row.offer_id) ?? 0) * row.rank,
      feature_trait,
      feature_marking,
    });
  });
  return shown;
}
