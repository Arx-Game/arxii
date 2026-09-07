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
    result.push({ id: entry.distinction_id, rank: entry.rank, offer_id: offerId });
  }
  return result;
}
