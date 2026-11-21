/**
 * StrengthStep (#5231, screens 1 and 2 of the approved demo): the Gift stage's resonance step.
 * Three answers: the feeling that gives the character strength, whether what she does to other
 * people gives her strength too (helping them, hurting them, or neither) and which resonance
 * on that side, and the balance between the two, with the aura the balance makes drawn
 * beside it.
 *
 * Every change writes one whole list, so the server never sees a list it refuses: changing
 * the side replaces the second pick in the same write, and "Neither" sends the feeling alone
 * holding every point. The server owns the rule; `resonanceWeights.ts` keeps this in step.
 */

import { useId } from 'react';
import { AuraSwirl } from '@/magic/components/AuraSwirl';
import type { CGExplanations, Resonance, ResonanceWeightPick } from '../../types';
import {
  affinityOfLean,
  mainAffinityOf,
  picksFromWeights,
  weightsFromPicks,
  type Lean,
  type StrengthPicks,
} from '../../resonanceWeights';

interface StrengthStepProps {
  resonances: Resonance[];
  weights: ResonanceWeightPick[];
  /** The points to divide: the server's creation points, never a number kept here. */
  budget: number;
  copy: CGExplanations | undefined;
  onChange: (weights: ResonanceWeightPick[]) => void;
}

/** The share of the budget a second pick gets when it is first chosen, as the demo does. */
const FIRST_OUTWARD_SHARE = 0.3;

const LEANS: { lean: Lean; key: string; fallback: string }[] = [
  { lean: 'give', key: 'gift_strength_answer_helping', fallback: 'Helping them' },
  { lean: 'take', key: 'gift_strength_answer_hurting', fallback: 'Hurting them' },
  { lean: 'none', key: 'gift_strength_answer_neither', fallback: 'Neither' },
];

interface CardsProps {
  label: string;
  resonances: Resonance[];
  picked: number | null;
  onPick: (id: number) => void;
}

function ResonanceCards({ label, resonances, picked, onPick }: CardsProps) {
  return (
    <div className="strength-opts" role="group" aria-label={label}>
      {resonances.map((resonance) => (
        <button
          key={resonance.id}
          type="button"
          className="strength-opt"
          aria-pressed={resonance.id === picked}
          onClick={() => onPick(resonance.id)}
        >
          <b>
            <i
              className="strength-sw"
              aria-hidden="true"
              style={{ background: resonance.color_hex }}
            />
            {resonance.name}
          </b>
          <span>{resonance.description}</span>
        </button>
      ))}
    </div>
  );
}

/** "a Celestial", "an Abyssal": the side word with its article. */
function withArticle(affinity: string): string {
  return `${/^[AEIOU]/.test(affinity) ? 'an' : 'a'} ${affinity}`;
}

export function StrengthStep({ resonances, weights, budget, copy, onChange }: StrengthStepProps) {
  const sliderId = useId();
  const pointsId = useId();
  const picks = picksFromWeights(weights, resonances, budget);
  const text = (key: string, fallback: string) => copy?.[key] ?? fallback;

  const primalCards = resonances.filter((resonance) => resonance.affinity_name === 'Primal');
  const sideCards = (lean: 'give' | 'take') =>
    resonances.filter((resonance) => resonance.affinity_name === affinityOfLean(lean));
  const nameOf = (id: number | null) => resonances.find((resonance) => resonance.id === id);

  const save = (next: StrengthPicks) => onChange(weightsFromPicks(next, budget));

  const chooseLean = (lean: Lean) => {
    if (lean === 'none') {
      save({ primal: picks.primal, lean, outward: null, primalPoints: budget });
      return;
    }
    // A pick already on this side stays; a new side starts at its first card, and a feeling
    // that held every point gives up a share to it (the demo's 7 of 10).
    const kept = lean === picks.lean ? picks.outward : null;
    const outward = kept ?? sideCards(lean)[0]?.id ?? null;
    const heldAll = picks.lean === 'none' || picks.outward == null;
    const primalPoints = heldAll
      ? budget - Math.max(1, Math.round(budget * FIRST_OUTWARD_SHARE))
      : picks.primalPoints;
    save({ primal: picks.primal, lean, outward, primalPoints });
  };

  const feeling = nameOf(picks.primal);
  const outward = picks.lean === 'none' ? undefined : nameOf(picks.outward);
  const skipped = picks.lean === 'none' || outward == null;
  const outwardPoints = skipped ? 0 : budget - picks.primalPoints;
  const main = mainAffinityOf(picks, budget);
  const otherSide =
    main === 'Primal' && picks.lean !== 'none' ? affinityOfLean(picks.lean) : 'Primal';
  const auraName = skipped ? 'Primal' : `${main}, with ${withArticle(otherSide)} side`;
  let said = text('gift_strength_aura_all_feeling', 'All your strength comes from what you feel.');
  if (!skipped && main === 'Primal') {
    said = text(
      'gift_strength_aura_mostly_feeling',
      'Most of your strength comes from what you feel.'
    );
  } else if (!skipped) {
    said = text(
      'gift_strength_aura_mostly_others',
      'Most of your strength comes from what you do to others.'
    );
  }
  const pointsLine = skipped
    ? `${feeling?.name ?? ''} ${budget}`
    : `${feeling?.name ?? ''} ${picks.primalPoints} · ${outward.name} ${outwardPoints}`;

  return (
    <div className="strength-step">
      <h3 className="strength-heading">
        {text('gift_strength_heading', 'Where your strength comes from')}
      </h3>
      <p className="strength-intro">
        {text('gift_strength_intro', 'Resonance is what powers your magic.')}
      </p>

      <p className="strength-ask">
        {text('gift_strength_feeling_question', 'Which feeling gives you strength')}
      </p>
      <ResonanceCards
        label={text('gift_strength_feeling_question', 'Which feeling gives you strength')}
        resonances={primalCards}
        picked={picks.primal}
        onPick={(id) => save({ ...picks, primal: id })}
      />

      {feeling && (
        <>
          <p className="strength-ask">
            {text(
              'gift_strength_others_question',
              'Does what you do to other people give you strength'
            )}
          </p>
          <div className="strength-row">
            {LEANS.map(({ lean, key, fallback }) => (
              <button
                key={lean}
                type="button"
                aria-pressed={picks.lean === lean}
                onClick={() => chooseLean(lean)}
              >
                {text(key, fallback)}
              </button>
            ))}
          </div>

          {picks.lean !== 'none' && (
            <>
              <p className="strength-ask">
                {text('gift_strength_outward_question', 'Which of these gives you strength')}
              </p>
              <ResonanceCards
                label={text('gift_strength_outward_question', 'Which of these gives you strength')}
                resonances={sideCards(picks.lean)}
                picked={picks.outward}
                onPick={(id) => save({ ...picks, outward: id })}
              />
            </>
          )}

          <p className="strength-ask">
            {text('gift_strength_balance_question', 'Which gives you more strength')}
          </p>
          <div className="strength-balance">
            <div className="strength-plate">
              <AuraSwirl
                className="strength-aura"
                primaryHex={feeling.color_hex}
                secondaryHex={skipped ? null : outward.color_hex}
                secondShare={outwardPoints / budget}
              />
              <p className="strength-named">{auraName}</p>
              <p className="strength-said">{said}</p>
            </div>
            <div className="strength-slide">
              <label htmlFor={sliderId}>
                <span>{text('gift_strength_slider_feeling', 'What you feel')}</span>
                <span>{text('gift_strength_slider_others', 'What you do to others')}</span>
              </label>
              <input
                id={sliderId}
                type="range"
                min={1}
                max={budget - 1}
                step={1}
                value={skipped ? 1 : outwardPoints}
                disabled={skipped}
                aria-describedby={pointsId}
                onChange={(event) =>
                  save({ ...picks, primalPoints: budget - Number(event.target.value) })
                }
              />
              <div className="strength-pts" id={pointsId}>
                {pointsLine}
              </div>
              {skipped && (
                <p className="strength-skipped">
                  {text(
                    'gift_strength_skipped',
                    'With no second pick there is nothing to balance. All {points} points go to the feeling.'
                  ).replace('{points}', String(budget))}
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
