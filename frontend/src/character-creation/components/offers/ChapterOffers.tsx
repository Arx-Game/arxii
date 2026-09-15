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
import { choiceEntries, sameFeature } from './syncHelpers';

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
  wordAwards?: string;
  /**
   * The fold (#3709): with `firstLook` (default true) a block of `foldUnder`
   * (default 5) or more offers shows the Beginning's pinned lines at rest, or
   * the first three by the server's order when none is pinned, and the rest
   * under one "See N more" line (`wordSeeMore`, with `{count}` filled in). A
   * shorter block never folds. `wordHeld` prints on a line whose distinction
   * the draft already holds from another offer.
   */
  firstLook?: boolean;
  foldUnder?: number;
  wordSeeMore?: string;
  wordHeld?: string;
}

interface PriceWords {
  perRank: string;
  spent: string;
  awards: string;
}

/** Lines shown at rest when a folding block has no pinned line (#3709 fork a). */
const FIRST_LOOK_FALLBACK = 3;
/** A block shorter than this never folds (#3709 fork e). */
const FOLD_UNDER = 5;

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
        <span className={offer.cost_per_rank < 0 ? 'award' : 'cost'}>
          {offer.cost_per_rank} {words.perRank}
        </span>
        {rank > 0 && (
          <span className={spent < 0 ? 'award' : 'cost'}>
            {spent} {words.spent}
          </span>
        )}
      </>
    );
  }
  if (offer.cost_per_rank < 0) {
    return (
      <span className="award">
        {words.awards} {-offer.cost_per_rank}
      </span>
    );
  }
  return <span className="cost">{offer.cost_per_rank}</span>;
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
      <span className={item.cost_per_rank < 0 ? 'award' : 'cost'}>
        {item.cost_per_rank} {words.perRank}
      </span>
    );
  }
  if (item.cost_per_rank < 0) {
    return (
      <span className="award">
        {words.awards} {-item.cost_per_rank}
      </span>
    );
  }
  return <span className="cost">{item.cost_per_rank}</span>;
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
  wordAwards,
  firstLook = true,
  foldUnder = FOLD_UNDER,
  wordSeeMore,
  wordHeld,
}: ChapterOffersProps) {
  const { data: offersData, isLoading } = useDraftOffers(draft.id, chapter);
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const syncDistinctions = useSyncDistinctions(draft.id);
  const priceWords: PriceWords = {
    perRank: wordPerRank ?? 'per rank',
    spent: wordSpent ?? 'spent',
    awards: wordAwards ?? 'Awards',
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
      // Only the plain (featureless) row for this distinction is replaced (#3739):
      // a per-feature holding of the same distinction is a different pick, and
      // `FeatureDistinctions` owns it.
      const base = choiceEntries(draftDistinctions).filter(
        (e) => !(e.id === offer.distinction_id && sameFeature(e, {}))
      );
      const next =
        rank > 0
          ? [
              ...base,
              // Explicitly featureless (#3739): every row in the payload carries
              // the same shape, so nothing here depends on a server-side default.
              {
                id: offer.distinction_id,
                rank,
                offer_id: offer.offer_id,
                feature_trait: '',
                feature_marking: 0,
              },
            ]
          : base;
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

  // The fold (#3709): the Beginning's pinned lines show at rest; when none is
  // pinned the first three by the server's order stand in; everything else waits
  // under one "See N more" line. A short block never folds.
  let atRest = offers;
  let folded: VisibleOffer[] = [];
  if (firstLook && offers.length >= foldUnder) {
    const pinned = offers.filter((o) => o.first_look);
    atRest = pinned.length > 0 ? pinned : offers.slice(0, FIRST_LOOK_FALLBACK);
    folded =
      pinned.length > 0 ? offers.filter((o) => !o.first_look) : offers.slice(FIRST_LOOK_FALLBACK);
  }
  const seeMore = (wordSeeMore ?? 'See {count} more').replace('{count}', String(folded.length));

  const renderOffer = (offer: VisibleOffer) => {
    const entry = entryByOfferId.get(offer.offer_id);
    const rank = entry?.rank ?? 0;
    const selected = rank > 0;
    const ranked = offer.max_rank > 1;
    const busy = offer.is_locked || syncDistinctions.isPending;
    const body = (
      <>
        <span className="dot sq" />
        <span>
          <b>
            {offer.name}
            {ranked && !offer.held && (
              <RankControl
                name={offer.name}
                rank={rank}
                max={offer.max_rank}
                disabled={busy}
                onChange={(next) => applyRank(offer, next)}
              />
            )}
          </b>
          <span className="g">
            {offer.player_line}
            {showOpener && offer.opener_label && <i> From {offer.opener_label}.</i>}
          </span>
          {offer.effect_line && <span className="fx">{offer.effect_line}</span>}
          {offer.is_locked && <span className="locked">{offer.lock_reason}</span>}
        </span>
        <span className="price">
          {offer.held && <span className="locked">{wordHeld ?? 'held'}</span>}
          <PriceLine offer={offer} rank={rank} words={priceWords} />
        </span>
      </>
    );
    // Held elsewhere (#3709): the draft already has this distinction from
    // another line, so this one reads held and offers no toggle.
    if (offer.held) {
      return (
        <li key={offer.offer_id}>
          <div className="stance" aria-pressed="true" aria-disabled="true">
            {body}
          </div>
        </li>
      );
    }
    return (
      <li key={offer.offer_id}>
        {ranked ? (
          <div
            className="stance"
            role="group"
            aria-label={offer.name}
            aria-disabled={busy || undefined}
          >
            {body}
          </div>
        ) : (
          <button
            type="button"
            className="stance"
            aria-pressed={selected}
            aria-disabled={busy || undefined}
            disabled={busy}
            onClick={() => applyRank(offer, selected ? 0 : 1)}
          >
            {body}
          </button>
        )}
      </li>
    );
  };

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
        {atRest.map(renderOffer)}
      </ul>
      {folded.length > 0 && (
        <details className="more">
          <summary>{seeMore}</summary>
          <ul className="stances">{folded.map(renderOffer)}</ul>
        </details>
      )}
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
