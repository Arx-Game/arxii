/**
 * ChapterOffers (#3675), the reusable offers block every CG chapter mounts
 * in place of the retired Distinctions stage.
 *
 * A chapter (the tradition step, the Glimpse, Lineage, Appearance, the
 * Actor's Sheet) asks `useDraftOffers(draft.id, chapter)` for its own
 * visible/closed distinctions and hands them here. Selection reads
 * `useDraftDistinctions` (an offer is picked when a draft entry's
 * `offer_ids` includes it) and writes through `useSyncDistinctions`
 * immediately on toggle or rank change, there is no deferred save: the
 * stage that deferred is gone. Every current CHOICE entry (one whose
 * `arrivals` list actually contains `'choice'`, `syncHelpers.choiceOfferId`)
 * is resent on every sync so a toggle in one chapter never drops another
 * chapter's picks; carried and bundled-only entries are never sent, the
 * server reconciles those itself.
 *
 * Wraps ITSELF in the folio `.field`; callers pass `heading`/`hint` as
 * props and never wrap this component in a `.field` of their own. A caller
 * that needs an extra class on that same div (Lineage's `.field.conditional`
 * shape, #3675 fix round 1) passes `className`, merged onto `.field` -
 * never wraps this component in a second div of its own.
 */

import { useCallback, useMemo } from 'react';
import { useDraftDistinctions, useSyncDistinctions } from '@/hooks/useDistinctions';
import { cn } from '@/lib/utils';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { useDraftOffers } from '../../queries';
import type { CharacterDraft, ClosedDistinction, OfferChapter, VisibleOffer } from '../../types';
import { RankControl } from './RankControl';
import { choiceEntries } from './syncHelpers';

interface ChapterOffersProps {
  draft: CharacterDraft;
  chapter: OfferChapter;
  /** Scope the chapter's offers to one axis's tags via `opener_label` (the Glimpse). */
  filter?: (offer: VisibleOffer) => boolean;
  /** Staff copy printed above the list, e.g. a question label. */
  heading?: string;
  /**
   * A `.tags > .tag.soft` chip printed right after `heading`, e.g. "optional"
   * (#3675 fix round 2, the demo marks every per-tag offer heading this
   * way). Omitted when `heading` itself is omitted.
   */
  headingTag?: string;
  /** Staff copy printed below the list, e.g. an explanatory note. */
  hint?: string;
  /**
   * Print the "From {opener_label}." attribution line. Defaults to true;
   * pass false when the caller's own `heading` already disambiguates which
   * tag opened the offer (the Glimpse's one-sub-block-per-tag layout,
   * #3675 fix round 1; the attribution line was compensating for the
   * per-axis heading that merged multiple tags' offers together).
   */
  showOpener?: boolean;
  /**
   * Lead-in phrase for the closed-offers hint, e.g. "Closed on this road".
   * Threaded from the caller's own copy query (mirrors `heading`/`hint`)
   * rather than read here; defaults to "Closed on this road".
   */
  closedLead?: string;
  /**
   * Scope the closed-offers hint to one axis's tag via `opener_labels`
   * (#3675 fix round 2, `closed_for` is now chapter-scoped but still
   * returns the route's whole closed list; a chapter with several sub-blocks,
   * like the Glimpse's one-per-tag layout, filters here so a closed item
   * prints once, under the tag that would have opened it, not under every
   * tag). Default: show every closed item this chapter's `useDraftOffers`
   * response carries.
   */
  closedFilter?: (closed: ClosedDistinction) => boolean;
  /**
   * Print the closed-offers hint. Defaults to true; pass false when the
   * caller renders its own once-per-chapter closed note elsewhere (Lineage's
   * `ClosedByRoute`, #3675 Task 14) so a mount under one answer doesn't
   * repeat the whole route's closed list.
   */
  showClosed?: boolean;
  /**
   * Locked "bundled" stances rendered BEFORE the offered ones, no toggle or
   * rank control - the answer already granted these for free (or a refund),
   * this just shows what arrived (#3675 Task 14). `player_line` is optional:
   * a bundled distinction's own line, when the caller has it. Keyed by
   * `offer_id`, the same id the offered rows key by (never the name - #3676).
   */
  bundled?: {
    offer_id: number;
    name: string;
    player_line?: string;
    cost_per_rank: number;
    max_rank: number;
  }[];
  /**
   * Merged onto this component's own `.field` div (#3675 fix round 1) so a
   * caller that needs the demo's `.field.conditional` shape (Lineage's
   * `ChosenAnswerOffers`) doesn't have to wrap this component in a second,
   * redundant div.
   */
  className?: string;
  /**
   * `.hint` line printed when the sync mutation fails (#3675 final fix F2).
   * Threaded from the caller's own copy query (mirrors `closedLead`) off
   * copy key `offers_sync_error`; defaults to 'That pick did not save. Try
   * again.'.
   */
  syncErrorHint?: string;
  /**
   * The price-grammar words below (#3675 final fix F5), each threaded from
   * the caller's own copy query the same way `closedLead` is; every default
   * is the word that printed before this fix, so the demo-fidelity
   * assertions still hold with no caller override at all.
   */
  wordBundled?: string;
  wordPerRank?: string;
  wordSpent?: string;
  wordRefunds?: string;
}

interface PriceWords {
  perRank: string;
  spent: string;
  refunds: string;
}

/** The price line: per-rank (plus a spent/refund total once picked) for a
 * ranked offer, a refund, or the flat cost for an unranked one. */
function PriceLine({
  offer,
  rank,
  words,
}: {
  offer: VisibleOffer;
  rank: number;
  words: PriceWords;
}) {
  if (offer.max_rank > 1) {
    const spent = offer.cost_per_rank * rank;
    return (
      <>
        <span>
          {offer.cost_per_rank} {words.perRank}
        </span>
        {rank > 0 && (
          <span className={spent < 0 ? 'refund' : undefined}>
            {spent} {words.spent}
          </span>
        )}
      </>
    );
  }
  if (offer.cost_per_rank < 0) {
    return (
      <span className="refund">
        {words.refunds} {-offer.cost_per_rank}
      </span>
    );
  }
  return <span>{offer.cost_per_rank}</span>;
}

/** The price line for a `bundled` row: same shape as `PriceLine`, off a
 * plain `{cost_per_rank, max_rank}` pair rather than a full `VisibleOffer` -
 * a bundled distinction carries no rank state of its own to spend against. */
function BundledPriceLine({
  item,
  words,
}: {
  item: { cost_per_rank: number; max_rank: number };
  words: PriceWords;
}) {
  if (item.max_rank > 1) {
    return (
      <span>
        {item.cost_per_rank} {words.perRank}
      </span>
    );
  }
  if (item.cost_per_rank < 0) {
    return (
      <span className="refund">
        {words.refunds} {-item.cost_per_rank}
      </span>
    );
  }
  return <span>{item.cost_per_rank}</span>;
}

export function ChapterOffers({
  draft,
  chapter,
  filter,
  heading,
  headingTag,
  hint,
  showOpener = true,
  closedLead,
  closedFilter,
  showClosed = true,
  bundled = [],
  className,
  syncErrorHint,
  wordBundled,
  wordPerRank,
  wordSpent,
  wordRefunds,
}: ChapterOffersProps) {
  const { data: offersData, isLoading } = useDraftOffers(draft.id, chapter);
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const syncDistinctions = useSyncDistinctions(draft.id);
  const priceWords: PriceWords = {
    perRank: wordPerRank ?? 'per rank',
    spent: wordSpent ?? 'spent',
    refunds: wordRefunds ?? 'Refunds',
  };

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
  const closed = (offersData?.closed ?? []).filter((c) => (closedFilter ? closedFilter(c) : true));

  if (offers.length === 0 && closed.length === 0 && bundled.length === 0) return null;

  return (
    <div className={cn('field', className)}>
      {heading && (
        <label>
          {heading}
          {headingTag && (
            <span className="tags">
              <span className="tag soft">{headingTag}</span>
            </span>
          )}
        </label>
      )}
      <ul className="stances">
        {bundled.map((item) => (
          <li key={item.offer_id}>
            <div className="stance" aria-pressed="true" aria-disabled="true">
              <span className="dot sq" />
              <span>
                <b>{item.name}</b>
                {item.player_line && <span className="g">{item.player_line}</span>}
              </span>
              <span className="price">
                <span className="locked">{wordBundled ?? 'bundled'}</span>
                <BundledPriceLine item={item} words={priceWords} />
              </span>
            </div>
          </li>
        ))}
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
                    <RankControl
                      name={offer.name}
                      rank={rank}
                      max={offer.max_rank}
                      disabled={offer.is_locked || syncDistinctions.isPending}
                      onChange={(next) => applyRank(offer, next)}
                    />
                  )}
                </b>
                <span className="g">
                  {offer.player_line}
                  {showOpener && offer.opener_label && <i> From {offer.opener_label}.</i>}
                </span>
                {offer.is_locked && <span className="locked">{offer.lock_reason}</span>}
              </span>
              <span className="price">
                <PriceLine offer={offer} rank={rank} words={priceWords} />
              </span>
            </>
          );
          return (
            <li key={offer.offer_id}>
              {ranked ? (
                <div
                  className="stance"
                  role="group"
                  aria-label={offer.name}
                  aria-disabled={offer.is_locked || syncDistinctions.isPending || undefined}
                >
                  {body}
                </div>
              ) : (
                <button
                  type="button"
                  className="stance"
                  aria-pressed={selected}
                  aria-disabled={offer.is_locked || syncDistinctions.isPending || undefined}
                  disabled={offer.is_locked || syncDistinctions.isPending}
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
      {syncDistinctions.isError && (
        <span className="hint">{syncErrorHint ?? 'That pick did not save. Try again.'}</span>
      )}
      {showClosed && closed.length > 0 && (
        <span className="hint">
          {`${closedLead ?? 'Closed on this road'}: ${closed
            .map((c) => `${c.name}: ${c.reason}`)
            .join('; ')}`}
        </span>
      )}
    </div>
  );
}
