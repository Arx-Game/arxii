/**
 * The per-feature Appearance rows (#3739): "Make it distinctive", then the
 * three presence axes it opens.
 *
 * `ChapterOffers` mounts a chapter's offers once, under a section. These
 * offers are different in kind: one authored line is offered on *every*
 * feature the character has, and the draft can hold it once per feature. So
 * this component mounts once per feature (a trait row in `AppearanceStage`,
 * a marking in `MarkingsEditor`), reads the same cached chapter query, and
 * writes through the same `useSyncDistinctions` payload -- with the feature
 * carried on the row, which is what keeps "Alluring on your eyes" and
 * "Alluring on your scar" apart.
 *
 * The unlock is the whole gate: until it is held on this feature, the axes
 * are not offered, the palette stays the species' own, and (for a trait) the
 * description field is closed. Refund it and the axes bought under it go with
 * it -- the server's `reconcile_offer_picks` drops them, so a stale rank never
 * outlives the point that paid for it.
 */

import { useCallback, useMemo } from 'react';
import { useDraftDistinctions, useSyncDistinctions } from '@/hooks/useDistinctions';
import type { DraftDistinctionEntry } from '@/types/distinctions';
import { useDraftOffers } from '../../queries';
import type { CharacterDraft, VisibleOffer } from '../../types';
import { RankControl } from './RankControl';
import { choiceEntries, sameFeature, type FeatureRef } from './syncHelpers';

interface FeatureDistinctionsProps {
  draft: CharacterDraft;
  /** The feature these rows are aimed at: a trait name, or a draft marking id. */
  feature: FeatureRef;
  /** Accessible name of the thing being made distinctive, e.g. "Eye Colour". */
  featureLabel: string;
  /** Copy for the unlock row; defaults match the approved demo's wording. */
  unlockLabel?: string;
  unlockWhy?: string;
  /** Copy for the axis price line, e.g. "2 per tier". */
  perTierWord?: string;
}

/** An entry's rank for one offer on one feature; 0 when not held. */
function rankFor(
  entries: DraftDistinctionEntry[] | undefined,
  offer: VisibleOffer,
  feature: FeatureRef
): number {
  const held = (entries ?? []).find(
    (e) => e.distinction_id === offer.distinction_id && sameFeature(e, feature)
  );
  return held?.rank ?? 0;
}

export function FeatureDistinctions({
  draft,
  feature,
  featureLabel,
  unlockLabel,
  unlockWhy,
  perTierWord,
}: FeatureDistinctionsProps) {
  const { data: offersData } = useDraftOffers(draft.id, 'appearance');
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const syncDistinctions = useSyncDistinctions(draft.id);

  const featureOffers = useMemo(
    () => (offersData?.offers ?? []).filter((o) => o.taken_per_feature),
    [offersData]
  );
  const unlock = featureOffers.find((o) => o.opens_feature);
  const axes = featureOffers.filter((o) => o.requires_feature_opened);

  const applyRank = useCallback(
    (offer: VisibleOffer, rank: number) => {
      const base = choiceEntries(draftDistinctions).filter(
        (e) => !(e.id === offer.distinction_id && sameFeature(e, feature))
      );
      const next =
        rank > 0
          ? [
              ...base,
              {
                id: offer.distinction_id,
                rank,
                offer_id: offer.offer_id,
                feature_trait: feature.feature_trait ?? '',
                feature_marking: feature.feature_marking ?? 0,
              },
            ]
          : base;
      syncDistinctions.mutate(next);
    },
    [draftDistinctions, feature, syncDistinctions]
  );

  const unlockRank = unlock ? rankFor(draftDistinctions, unlock, feature) : 0;

  // Dropping the unlock drops every axis bought on this feature in the same
  // write, so the client never sends the server a payload it would refuse.
  const toggleUnlock = useCallback(() => {
    if (!unlock) return;
    if (unlockRank > 0) {
      syncDistinctions.mutate(
        choiceEntries(draftDistinctions).filter((e) => !sameFeature(e, feature))
      );
      return;
    }
    applyRank(unlock, 1);
  }, [applyRank, draftDistinctions, feature, syncDistinctions, unlock, unlockRank]);

  if (!unlock) return null;

  // The unlock and each axis are ordinary `.stance` rows (the folio's one offer
  // grammar), so a feature block reads like every other priced line in CG; only
  // the `.opened` wrapper and the axis pips are new (#3739).
  return (
    <ul className="stances feature-buy">
      <li>
        <button
          type="button"
          className="stance"
          aria-pressed={unlockRank > 0}
          onClick={toggleUnlock}
        >
          <span className="dot" />
          <b>
            {unlockLabel ?? 'Make it distinctive'}
            {unlockWhy && <span className="g">{unlockWhy}</span>}
          </b>
          <span className="price">
            <span className="cost">{unlock.cost_per_rank}</span>
          </span>
        </button>
      </li>
      {unlockRank > 0 &&
        axes.map((axis) => {
          const rank = rankFor(draftDistinctions, axis, feature);
          const max = axis.cg_max_rank || axis.max_rank;
          return (
            <li key={axis.offer_id} className="opened">
              <div className="stance ax" role="group" aria-label={`${axis.name} on ${featureLabel}`}>
                <span className="dot sq" />
                <b>
                  {axis.name}
                  <span className="tiers" aria-hidden="true">
                    {Array.from({ length: max }, (_, i) => (
                      <span key={i} className={i < rank ? 'tier on' : 'tier'} />
                    ))}
                  </span>
                  <RankControl
                    name={`${axis.name} on ${featureLabel}`}
                    rank={rank}
                    max={max}
                    onChange={(next) => applyRank(axis, next)}
                  />
                </b>
                <span className="price">
                  <span className="cost">
                    {axis.cost_per_rank} {perTierWord ?? 'per tier'}
                  </span>
                  {rank > 0 && <span className="cost">{axis.cost_per_rank * rank} spent</span>}
                </span>
              </div>
            </li>
          );
        })}
    </ul>
  );
}
