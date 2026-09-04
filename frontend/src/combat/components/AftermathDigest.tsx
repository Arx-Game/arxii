/**
 * AftermathDigest — per-participant post-encounter digest (#3551).
 *
 * Rendered under EncounterOutcomeBanner once an encounter concludes: the
 * consequence roulette, conditions carried out of the fight, legend earned,
 * how the running beat resolved, and whether peril is still tracked in scene
 * rounds. A GM sees one digest per participant carrying a non-null
 * aftermath payload; a player sees only their own — that split is driven
 * purely by which participants the server sends an aftermath for, not by a
 * permission check in this component.
 *
 * Legend is reported plainly ("Deed remembered") — never framed as a fight
 * payout; it settles at the end, per the bards-make-songs test.
 */

import { OutcomeRoulette } from '../OutcomeRoulette';
import { ConditionBadge } from './ConditionBadge';
import type { components } from '@/generated/api';

export type AftermathDigest = NonNullable<components['schemas']['Participant']['aftermath']>;

export interface AftermathDigestProps {
  digest: AftermathDigest;
  /** Character name header — shown only when the viewer sees several digests at once. */
  title?: string;
}

export function AftermathDigest({ digest, title }: AftermathDigestProps) {
  const { consequence, conditions, legend, beat, peril_round_active: perilRoundActive } = digest;
  const beatText = beat
    ? `${beat.resolution_text || 'The beat is resolved'} (${beat.tier_name ?? 'ungraded'}, ${beat.outcome})`
    : null;

  return (
    <div className="space-y-3" data-testid="aftermath-digest">
      {title && <h3 className="text-sm font-semibold text-foreground">{title}</h3>}

      {consequence && (
        <div data-testid="aftermath-consequence">
          <OutcomeRoulette
            outcomeDisplay={consequence.outcome_display}
            modifiers={consequence.modifiers}
            modifierTotal={consequence.modifier_total}
            summary={consequence.summary}
          />
        </div>
      )}

      {conditions.length > 0 && (
        <div className="space-y-1" data-testid="aftermath-conditions">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            You carry out of the fight
          </p>
          <div className="flex flex-wrap gap-1">
            {conditions.map((condition) => (
              <ConditionBadge key={condition.id} condition={condition} />
            ))}
          </div>
        </div>
      )}

      {legend.length > 0 && (
        <div className="space-y-1" data-testid="aftermath-legend">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Deed remembered
          </p>
          {legend.map((entry, index) => (
            <p key={`${entry.title}-${index}`} className="text-xs text-foreground">
              {entry.title} (+{entry.base_value} legend)
            </p>
          ))}
        </div>
      )}

      {beatText && (
        <p className="text-xs text-muted-foreground" data-testid="aftermath-beat">
          {beatText}
        </p>
      )}

      {perilRoundActive && (
        <p className="text-xs text-amber-300" data-testid="aftermath-peril">
          Your peril is not over: a scene round now tracks it.
        </p>
      )}
    </div>
  );
}
