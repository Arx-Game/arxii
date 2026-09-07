/**
 * Sync-payload helpers shared by `ChapterOffers` and `SchoolingStances`
 * (#3675): both write the draft's CHOICE distinctions through
 * `useSyncDistinctions`, and both need to resend every current CHOICE entry
 * unchanged alongside the one row they are actually changing, so a toggle in
 * one chapter's offers never drops another chapter's picks.
 */

import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';

/** The first integer id in an entry's `offer_ids`, the CHOICE offer it came from, if any. */
export function choiceOfferId(entry: DraftDistinctionEntry): number | undefined {
  return entry.offer_ids.find((id): id is number => typeof id === 'number');
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
    result.push({ id: entry.distinction_id, rank: entry.rank, offer_id: offerId });
  }
  return result;
}
