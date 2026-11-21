/**
 * The qualities of one feature (#3739, #5241): Alluring, Menacing, Majestic, each
 * with its tiers on one thin line.
 *
 * `ChapterOffers` mounts a chapter's offers once, under a section. These offers
 * are different in kind: one authored line is offered on *every* feature the
 * character has, and the draft can hold it once per feature. So this component
 * mounts once per feature (a trait in `AppearanceStage`, a marking in
 * `MarkingsEditor`), reads the same cached chapter query, and writes through the
 * same `useSyncDistinctions` payload, with the feature carried on the row, which
 * is what keeps "Alluring on your eyes" and "Alluring on your scar" apart.
 *
 * A tier is one click, with nothing before it (owner ruling 2026-11-21: the
 * qualities could not be found behind "Make it distinctive", and one point buys
 * one tier with no unlock). A feature that holds any tier is distinctive: its
 * trait reaches every colour and its description opens. `onClosed` fires when a
 * click takes the last tier off the feature, so the caller can let go of what
 * only a distinctive feature may hold.
 *
 * The line is always on the page. It shows a click at once from the save in
 * flight (`pendingEntries`, #5134) and takes no second click until that save
 * answers, because a second save would be built from the list the first is
 * replacing.
 */

import { useCallback, useMemo } from 'react';
import { useDraftDistinctions, useSyncDistinctions } from '@/hooks/useDistinctions';
import type { DraftDistinctionEntry, SyncDistinctionEntry } from '@/types/distinctions';
import { useDraftOffers } from '../../queries';
import type { CharacterDraft, VisibleOffer } from '../../types';
import { choiceEntries, sameFeature, type FeatureRef } from './syncHelpers';

interface FeatureDistinctionsProps {
  draft: CharacterDraft;
  /** The feature these qualities are aimed at: a trait name, or a draft marking id. */
  feature: FeatureRef;
  /** Accessible name of the feature, e.g. "Eye Colour". */
  featureLabel: string;
  /** Called when a click takes the last tier of any quality off this feature. */
  onClosed?: () => void;
}

/** An offer's rank on one feature in a save's rows; 0 when the save does not hold it. */
function pendingRank(rows: SyncDistinctionEntry[], offer: VisibleOffer, feature: FeatureRef) {
  return rows.find((r) => r.offer_id === offer.offer_id && sameFeature(r, feature))?.rank ?? 0;
}

/** An offer's saved rank on one feature; 0 when not held. */
function savedRank(
  entries: DraftDistinctionEntry[] | undefined,
  offer: VisibleOffer,
  feature: FeatureRef
) {
  const held = (entries ?? []).find(
    (e) => e.distinction_id === offer.distinction_id && sameFeature(e, feature)
  );
  return held?.rank ?? 0;
}

export function FeatureDistinctions({
  draft,
  feature,
  featureLabel,
  onClosed,
}: FeatureDistinctionsProps) {
  const { data: offersData } = useDraftOffers(draft.id, 'appearance');
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);
  const syncDistinctions = useSyncDistinctions(draft.id);
  const pending = syncDistinctions.pendingEntries;

  const qualities = useMemo(
    () => (offersData?.offers ?? []).filter((o) => o.taken_per_feature),
    [offersData]
  );

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
      if (!next.some((e) => sameFeature(e, feature))) onClosed?.();
    },
    [draftDistinctions, feature, onClosed, syncDistinctions]
  );

  if (qualities.length === 0) return null;

  return (
    <ul className="qualities" aria-label={`Qualities of ${featureLabel}`}>
      {qualities.map((quality) => {
        const rank =
          pending !== null
            ? pendingRank(pending, quality, feature)
            : savedRank(draftDistinctions, quality, feature);
        const max = quality.cg_max_rank || quality.max_rank;
        const name = `${quality.name} on ${featureLabel}`;
        return (
          <li key={quality.offer_id} className={rank > 0 ? 'quality held' : 'quality'}>
            <span className="quality-name" title={quality.player_line || undefined}>
              {quality.name}
            </span>
            <span className="tiers" role="group" aria-label={name}>
              {Array.from({ length: max }, (_, i) => {
                const tier = i + 1;
                return (
                  <button
                    key={tier}
                    type="button"
                    className={tier <= rank ? 'tier on' : 'tier'}
                    aria-pressed={tier <= rank}
                    aria-label={`${name}, tier ${tier}`}
                    disabled={pending !== null}
                    // A press on the top tier held takes it off; any other sets that tier.
                    onClick={() => applyRank(quality, tier === rank ? tier - 1 : tier)}
                  />
                );
              })}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
