/**
 * ChapterOffers (#3675) — the reusable offers block every CG chapter mounts
 * in place of the retired Distinctions stage.
 *
 * A chapter (the tradition step, the Glimpse, Lineage, Appearance, the
 * Actor's Sheet) asks `useDraftOffers(draft.id, chapter)` for its own
 * visible/closed distinctions and hands them here. Selection reads
 * `useDraftDistinctions` (an offer is picked when a draft entry's
 * `offer_ids` includes it) and writes through `useSyncDistinctions`
 * immediately on toggle or rank change — there is no deferred save; the
 * stage that deferred is gone. Every current CHOICE entry (one with an
 * integer `offer_id`) is resent on every sync so a toggle in one chapter
 * never drops another chapter's picks; carried entries (string-only
 * `offer_ids`) and bundled entries are never sent — the server reconciles
 * those itself.
 */

import { useCallback, useMemo } from 'react';
import { useDraftDistinctions, useSyncDistinctions } from '@/hooks/useDistinctions';
import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';
import { useDraftOffers } from '../../queries';
import type { CharacterDraft, OfferChapter, VisibleOffer } from '../../types';

interface ChapterOffersProps {
  draft: CharacterDraft;
  chapter: OfferChapter;
  /** Scope the chapter's offers to one axis's tags via `opener_label` (the Glimpse). */
  filter?: (offer: VisibleOffer) => boolean;
  /** Staff copy printed above the list, e.g. a question label. */
  heading?: string;
  /** Staff copy printed below the list, e.g. an explanatory note. */
  hint?: string;
}

/** The first integer id in an entry's `offer_ids` — the CHOICE offer it came from, if any. */
function choiceOfferId(entry: DraftDistinctionEntry): number | undefined {
  return entry.offer_ids.find((id): id is number => typeof id === 'number');
}

/**
 * Every current CHOICE entry as a sync payload row. Carried entries (no
 * integer offer id) and bundled entries are dropped — the server re-applies
 * those on its own (`reconcile_offer_picks`).
 */
function choiceEntries(entries: DraftDistinctionEntry[] | undefined): SyncDistinctionEntry[] {
  const result: SyncDistinctionEntry[] = [];
  for (const entry of entries ?? []) {
    const offerId = choiceOfferId(entry);
    if (offerId === undefined) continue;
    result.push({ id: entry.distinction_id, rank: entry.rank, offer_id: offerId });
  }
  return result;
}

/** The price line: per-rank for a ranked offer, a refund, or the flat cost. */
function PriceLine({ offer }: { offer: VisibleOffer }) {
  if (offer.max_rank > 1) {
    return <span>{offer.cost_per_rank} per rank</span>;
  }
  if (offer.cost_per_rank < 0) {
    return <span className="refund">Refunds {-offer.cost_per_rank}</span>;
  }
  return <span>{offer.cost_per_rank}</span>;
}

export function ChapterOffers({ draft, chapter, filter, heading, hint }: ChapterOffersProps) {
  const { data: offersData, isLoading } = useDraftOffers(draft.id, chapter);
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const syncDistinctions = useSyncDistinctions(draft.id);

  const entryByOfferId = useMemo(() => {
    const map = new Map<number, DraftDistinctionEntry>();
    for (const entry of draftDistinctions ?? []) {
      for (const id of entry.offer_ids) {
        if (typeof id === 'number') map.set(id, entry);
      }
    }
    return map;
  }, [draftDistinctions]);

  const applyRank = useCallback(
    (offer: VisibleOffer, rank: number) => {
      const base = choiceEntries(draftDistinctions).filter((e) => e.id !== offer.distinction_id);
      const next =
        rank > 0 ? [...base, { id: offer.distinction_id, rank, offer_id: offer.offer_id }] : base;
      syncDistinctions.mutate(next);
    },
    [draftDistinctions, syncDistinctions]
  );

  if (isLoading) {
    return (
      <p className="ledger-line" aria-busy="true">
        Loading offers…
      </p>
    );
  }

  const offers = (offersData?.offers ?? []).filter((offer) => (filter ? filter(offer) : true));
  const closed = offersData?.closed ?? [];

  if (offers.length === 0 && closed.length === 0) return null;

  return (
    <>
      {heading && <label>{heading}</label>}
      <ul className="stances">
        {offers.map((offer) => {
          const entry = entryByOfferId.get(offer.offer_id);
          const rank = entry?.rank ?? 0;
          const selected = rank > 0;
          const ranked = offer.max_rank > 1;
          const body = (
            <>
              <span className="dot sq" />
              <span>
                <b>
                  {offer.name}
                  {ranked && (
                    <span className="rank" aria-label={`rank ${rank} of ${offer.max_rank}`}>
                      <button
                        type="button"
                        disabled={offer.is_locked || rank <= 0}
                        aria-label={`Lower ${offer.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          applyRank(offer, rank - 1);
                        }}
                      >
                        −
                      </button>
                      <button
                        type="button"
                        disabled={offer.is_locked || rank >= offer.max_rank}
                        aria-label={`Raise ${offer.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          applyRank(offer, rank + 1);
                        }}
                      >
                        +
                      </button>
                    </span>
                  )}
                </b>
                <span className="g">
                  {offer.player_line}
                  {offer.opener_label && <i> From {offer.opener_label}.</i>}
                </span>
                {offer.is_locked && <span className="locked">{offer.lock_reason}</span>}
              </span>
              <span className="price">
                <PriceLine offer={offer} />
              </span>
            </>
          );
          return (
            <li key={offer.offer_id}>
              {ranked ? (
                <div
                  className="stance"
                  aria-pressed={selected}
                  aria-disabled={offer.is_locked || undefined}
                >
                  {body}
                </div>
              ) : (
                <button
                  type="button"
                  className="stance"
                  aria-pressed={selected}
                  aria-disabled={offer.is_locked || undefined}
                  disabled={offer.is_locked}
                  onClick={() => applyRank(offer, selected ? 0 : 1)}
                >
                  {body}
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {hint && <span className="hint">{hint}</span>}
      {closed.length > 0 && (
        <span className="hint">
          Closed on this road: {closed.map((c) => c.name).join(', ')}. {closed[0].reason}
        </span>
      )}
    </>
  );
}
