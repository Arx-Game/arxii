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

import { useCallback, useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import { useDraftDistinctions, useSyncDistinctions } from '@/hooks/useDistinctions';
import { cn } from '@/lib/utils';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { useDraftOffers } from '../../queries';
import type {
  CharacterDraft,
  ClosedDistinction,
  OfferChapter,
  OfferTerm,
  VisibleOffer,
} from '../../types';
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
  /**
   * One-of (#4124): the block's offers are alternatives, drawn across as a row of
   * cards with a round dot, and picking one drops any sibling already picked. The
   * server refuses two answers on a one-of beat as well; this keeps the page in
   * step without a round trip.
   */
  exclusive?: boolean;
  /**
   * The life grids (#4395): every offer a card in a three-column grid, its own label
   * first and the distinction under it when the label is the author's own words.
   */
  layout?: 'list' | 'grid';
  /**
   * How many of this block's offers may be picked at once (#4395): an age-scaled
   * beat's allowance. At the allowance the unpicked cards read disabled; the server
   * refuses the extra pick as well. `null` or omitted is any number.
   */
  maxPicks?: number | null;
  /**
   * The block spends career points (#4829): `maxPicks` counts ranks, not cards, and a
   * ranked card shows its ranks as pips in its top right (a click sets the rank, the
   * pips past the points left are dimmed) instead of the +/- stepper.
   */
  pointsPicks?: boolean;
  /**
   * The life page (#4874, slice 9 of #4813). `groupBy` splits a grid under `.group-h`
   * headings, "Group (count)", in first-seen order, the ungrouped cards last with no
   * heading. `pricing="signed"` prints a grid card's price as a bare signed number in
   * its corner, `-N` in ink when you pay and `+N` in green when the world pays you,
   * nothing at all for a free card (Unremarkable); the default keeps the words the
   * list layouts print. `terms` turns the mechanics line into `+10 sailing; -5 martial`
   * built from `offer.effects`, each term a click that opens its definition.
   * `interceptPick` runs before a card click changes a pick; returning true means the
   * caller handled it (the cover-story flow: the next click after a secret mark sets
   * the cover instead of swapping). `coverOfferId` draws that card dashed.
   */
  groupBy?: (offer: VisibleOffer) => string;
  pricing?: 'words' | 'signed';
  terms?: OfferTerm[];
  interceptPick?: (offer: VisibleOffer, selected: boolean) => boolean;
  coverOfferId?: number | null;
  /** The picks on this block marked secret (#4874): each wears `wordSecret`; the cover
   * card wears `wordCover`. */
  secretOfferIds?: number[];
  wordSecret?: string;
  wordCover?: string;
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

/** A signed price (#4874): the number a life card wears in its corner. `-N` when you
 * pay, `+N` when the world pays you, nothing for a free card. */
function SignedPrice({ cost, rank }: { cost: number; rank: number }) {
  const total = cost * Math.max(rank, 1);
  if (total === 0) return null;
  return total < 0 ? (
    <span className="award">{`+${-total}`}</span>
  ) : (
    <span className="cost">{`\u2212${total}`}</span>
  );
}

/** What stands before a term on the mechanics line: the signed magnitude, the
 * immunity's words, or nothing for an effect with no number. */
function effectPrefix(effect: VisibleOffer['effects'][number]): string {
  if (effect.immune) return 'Immune to negative ';
  if (effect.value === null) return '';
  return `${effect.value < 0 ? '\u2212' : '+'}${Math.abs(effect.value)} `;
}

/** The mechanics line built from the effect rows (#4874): `+10 sailing; -5 martial`,
 * each term a button that opens its definition. An immunity reads as the list layouts
 * print it. */
function EffectTerms({
  offer,
  onTerm,
}: {
  offer: VisibleOffer;
  onTerm: (target: HTMLElement, name: string) => void;
}) {
  if (offer.effects.length === 0) return null;
  return (
    <span className="fx">
      {offer.effects.map((effect, i) => (
        <span key={`${effect.target}-${i}`}>
          {i > 0 && '; '}
          {effectPrefix(effect)}
          {/* A span with the button role: the card around it is already a button, and a
              button may not nest one. */}
          <span
            role="button"
            tabIndex={0}
            className="term"
            aria-label={`${effect.label}, definition`}
            onClick={(e) => {
              e.stopPropagation();
              onTerm(e.currentTarget, effect.target);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                onTerm(e.currentTarget, effect.target);
              }
            }}
          >
            {effect.label}
          </span>
        </span>
      ))}
    </span>
  );
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
  exclusive = false,
  layout = 'list',
  maxPicks = null,
  pointsPicks = false,
  groupBy,
  pricing = 'words',
  terms,
  interceptPick,
  coverOfferId = null,
  secretOfferIds = [],
  wordSecret,
  wordCover,
}: ChapterOffersProps) {
  const { data: offersData, isLoading } = useDraftOffers(draft.id, chapter);
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const syncDistinctions = useSyncDistinctions(draft.id);
  // The one open term popover (#4874): which term, and where its button sits.
  const [openTerm, setOpenTerm] = useState<{ name: string; top: number; left: number } | null>(
    null
  );
  useEffect(() => {
    if (!openTerm) return;
    const close = () => setOpenTerm(null);
    // A click inside the box keeps it; anything else closes it.
    const onClick = (e: MouseEvent) => {
      if (!(e.target instanceof Element && e.target.closest('.popover'))) close();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    document.addEventListener('click', onClick);
    document.addEventListener('keydown', onKey);
    window.addEventListener('scroll', close, { passive: true });
    return () => {
      document.removeEventListener('click', onClick);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('scroll', close);
    };
  }, [openTerm]);
  const showTerm = useCallback((target: HTMLElement, name: string) => {
    // Viewport coordinates, clamped so the box stays on screen (the demo's rule).
    const rect = target.getBoundingClientRect();
    const width = Math.min(352, window.innerWidth - 24);
    const left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12));
    const top = rect.bottom + 180 > window.innerHeight ? rect.top - 180 : rect.bottom + 6;
    setOpenTerm((current) => (current?.name === name ? null : { name, top, left }));
  }, []);
  const termDefinition = useMemo(() => {
    const map = new Map<string, OfferTerm>();
    for (const term of terms ?? []) map.set(term.name, term);
    return map;
  }, [terms]);
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

  // The block's own offer ids (#4124): an exclusive block drops a sibling pick when
  // another is taken.
  const blockOfferIds = useMemo(
    () =>
      new Set(
        (offersData?.offers ?? [])
          .filter((offer) => (filter ? filter(offer) : true))
          .map((offer) => offer.offer_id)
      ),
    [offersData, filter]
  );

  const applyRank = useCallback(
    (offer: VisibleOffer, rank: number) => {
      // Only the plain (featureless) row for this distinction is replaced (#3739):
      // a per-feature holding of the same distinction is a different pick, and
      // `FeatureDistinctions` owns it.
      const base = choiceEntries(draftDistinctions).filter(
        (e) =>
          !(e.id === offer.distinction_id && sameFeature(e, {})) &&
          !(exclusive && rank > 0 && blockOfferIds.has(e.offer_id))
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
    [draftDistinctions, syncDistinctions, exclusive, blockOfferIds]
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

  // The allowance (#4395): once this block holds as many picks as it allows, the rest
  // wait; an exclusive block swaps instead, so it never counts as full. A block that
  // spends career points (#4829) counts ranks: a rank-four card is four of them.
  const rankOf = (o: VisibleOffer) => entryByOfferId.get(o.offer_id)?.rank ?? 0;
  const pickedHere = pointsPicks
    ? offers.reduce((sum, o) => sum + rankOf(o), 0)
    : offers.filter((o) => rankOf(o) > 0).length;
  const full =
    !exclusive && maxPicks !== null && (pointsPicks || maxPicks > 1) && pickedHere >= maxPicks;
  // The points still free in this block, for the pips (#4829); null when nothing bounds it.
  const pointsLeft = pointsPicks && maxPicks !== null ? Math.max(0, maxPicks - pickedHere) : null;

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
  // The groups (#4874): headings in first-seen order, the ungrouped cards last under
  // none; without `groupBy` one unnamed group holds every card at rest.
  const grouped = new Map<string, VisibleOffer[]>();
  for (const offer of atRest) {
    const key = groupBy ? groupBy(offer) : '';
    const list = grouped.get(key) ?? [];
    list.push(offer);
    grouped.set(key, list);
  }
  const groups: [string, VisibleOffer[]][] = [
    ...[...grouped.entries()].filter(([key]) => key !== ''),
    ...[...grouped.entries()].filter(([key]) => key === ''),
  ];
  if (groups.length === 0) groups.push(['', []]);

  const renderOffer = (offer: VisibleOffer) => {
    const entry = entryByOfferId.get(offer.offer_id);
    const rank = entry?.rank ?? 0;
    const selected = rank > 0;
    const ranked = offer.max_rank > 1;
    const waiting = full && !selected;
    const busy = offer.is_locked || syncDistinctions.isPending || waiting;
    // Pips (#4829): on a career-point grid the rank is the pips in the card's top
    // right. A pip at or under the held rank is on; one past the points this card could
    // still take is off; a click sets that rank (the first pip of an unpicked card picks
    // it; the held rank's own pip clears it).
    const pips =
      pointsPicks && ranked && !offer.held
        ? Array.from({ length: offer.max_rank }, (_, i) => i + 1)
        : null;
    const reach = pointsLeft === null ? offer.max_rank : rank + pointsLeft;
    const showsDistinction =
      layout === 'grid' && offer.distinction_name && offer.distinction_name !== offer.name;
    const isCover = coverOfferId !== null && coverOfferId === offer.offer_id;
    const isSecret = secretOfferIds.includes(offer.offer_id);
    const toggle = () => {
      if (interceptPick?.(offer, selected)) return;
      applyRank(offer, selected ? 0 : 1);
    };
    const body = (
      <>
        <span className={exclusive ? 'dot' : 'dot sq'} />
        <span>
          <b>
            {offer.name}
            {ranked && !offer.held && !pips && (
              <RankControl
                name={offer.name}
                rank={rank}
                max={offer.max_rank}
                disabled={busy}
                onChange={(next) => applyRank(offer, next)}
              />
            )}
          </b>
          {showsDistinction && <span className="g">{offer.distinction_name}</span>}
          <span className="g">
            {offer.player_line}
            {showOpener && offer.opener_label && <i> From {offer.opener_label}.</i>}
          </span>
          {terms ? (
            <EffectTerms offer={offer} onTerm={showTerm} />
          ) : (
            offer.effect_line && <span className="fx">{offer.effect_line}</span>
          )}
          {offer.is_locked && <span className="locked">{offer.lock_reason}</span>}
          {isSecret && (
            <span className="secret">{wordSecret ?? 'Secret: select a cover story below'}</span>
          )}
          {isCover && <span className="secret">{wordCover ?? 'Cover story'}</span>}
        </span>
        <span className="price">
          {offer.held && <span className="locked">{wordHeld ?? 'held'}</span>}
          {pricing === 'signed' ? (
            <SignedPrice cost={offer.cost_per_rank} rank={rank} />
          ) : (
            <PriceLine offer={offer} rank={rank} words={priceWords} />
          )}
        </span>
        {pips && (
          <span
            className="pips"
            role="group"
            aria-label={`${offer.name}, rank ${rank} of ${offer.max_rank}`}
          >
            {pips.map((pip) => {
              const on = pip <= rank;
              const off = pip > reach;
              return (
                <button
                  key={pip}
                  type="button"
                  className={cn('pip', on && 'on', off && 'off')}
                  aria-pressed={on}
                  aria-label={`${offer.name}, rank ${pip}`}
                  disabled={(offer.is_locked || syncDistinctions.isPending || off) && !on}
                  onClick={(e) => {
                    e.stopPropagation();
                    applyRank(offer, pip === rank ? 0 : pip);
                  }}
                />
              );
            })}
          </span>
        )}
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
            className={cn('stance', pips && 'ranked', isCover && 'cover')}
            role="group"
            aria-label={offer.name}
            aria-disabled={busy || undefined}
          >
            {body}
          </div>
        ) : (
          <button
            type="button"
            className={cn('stance', isCover && 'cover')}
            aria-pressed={selected}
            aria-disabled={busy || undefined}
            disabled={busy && !interceptPick}
            onClick={toggle}
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
      {groups.map(([group, members]) => (
        <div key={group || '\u0000'} className="offer-group">
          {group && <div className="group-h">{`${group} (${members.length})`}</div>}
          <ul className={cn('stances', exclusive && 'oneof', layout === 'grid' && 'grid')}>
            {group === groups[0][0] &&
              bundled.map((item) => (
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
            {members.map(renderOffer)}
          </ul>
        </div>
      ))}
      {openTerm &&
        // Through a portal (#4874): the life block is a size container, which would
        // otherwise anchor a fixed box to itself instead of the viewport.
        createPortal(
          <dialog
            open
            className="interview popover"
            aria-label={termDefinition.get(openTerm.name)?.label ?? openTerm.name}
            style={{ top: openTerm.top, left: openTerm.left }}
          >
            <b>{termDefinition.get(openTerm.name)?.label ?? openTerm.name}</b>
            {termDefinition.get(openTerm.name)?.definition ?? ''}
          </dialog>,
          document.body
        )}
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
