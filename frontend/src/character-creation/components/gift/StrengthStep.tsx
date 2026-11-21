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

import { useId, useState } from 'react';
import { NEUTRAL_HEX } from '@/magic/auraSwirl';
import { AuraSwirl } from '@/magic/components/AuraSwirl';
import type { CGExplanations, Resonance, ResonanceWeightPick } from '../../types';
import {
  affinityOfLean,
  defaultPrimalPoints,
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

  // The side she has chosen but not yet picked a resonance on. The saved list cannot hold it
  // (a side is only written by its pick), so it is kept here until her pick arrives.
  const [pendingSide, setPendingSide] = useState<'give' | 'take' | null>(null);
  // Her answer about others: the saved second pick's side when there is one, else the side she
  // has just chosen, else what the saved list says.
  const lean: Lean | null = picks.outward != null ? picks.lean : (pendingSide ?? picks.lean);

  const chooseLean = (next: Lean) => {
    if (next === 'none') {
      setPendingSide(null);
      save({ ...picks, lean: next, outward: null, primalPoints: budget });
      return;
    }
    // A side gives her no card: she picks one herself. Only a second pick left over from the
    // other side is cleared, in one write.
    setPendingSide(next);
    if (picks.outward != null && picks.lean !== next) {
      save({ ...picks, lean: next, outward: null, primalPoints: budget });
    }
  };

  // A feeling that held every point gives up a share to the second pick (the demo's 7 of 10).
  const chooseOutward = (id: number) => {
    const primalPoints = picks.outward == null ? defaultPrimalPoints(budget) : picks.primalPoints;
    save({ ...picks, lean, outward: id, primalPoints });
  };

  const feeling = nameOf(picks.primal);
  const chosenSide = lean === 'give' || lean === 'take' ? lean : null;
  const outward = chosenSide && picks.lean === chosenSide ? nameOf(picks.outward) : undefined;
  // The balance exists once both picks do; before that the slider is off.
  const balanced = feeling != null && outward != null;
  const neither = picks.lean === 'none' && feeling != null;
  const outwardPoints = balanced ? budget - picks.primalPoints : 0;
  const main = mainAffinityOf(picks, budget);
  const otherSide = main === 'Primal' && chosenSide ? affinityOfLean(chosenSide) : 'Primal';
  // No name and no sentence before a feeling is chosen: the aura claims nothing she has not.
  let auraName: string | null = null;
  let said: string | null = null;
  if (neither) {
    auraName = 'Primal';
    said = text('gift_strength_aura_all_feeling', 'All your strength comes from what you feel.');
  } else if (balanced) {
    auraName = `${main}, with ${withArticle(otherSide)} side`;
    said =
      main === 'Primal'
        ? text(
            'gift_strength_aura_mostly_feeling',
            'Most of your strength comes from what you feel.'
          )
        : text(
            'gift_strength_aura_mostly_others',
            'Most of your strength comes from what you do to others.'
          );
  }
  let pointsLine = '';
  if (balanced) {
    pointsLine = `${feeling.name} ${picks.primalPoints} · ${outward.name} ${outwardPoints}`;
  } else if (neither) {
    pointsLine = `${feeling.name} ${budget}`;
  } else if (feeling || outward) {
    pointsLine = `${(feeling ?? outward)?.name} ${budget}`;
  }
  // The aura is drawn in the feeling's colour, the second pick's when only it is chosen, and
  // the neutral grey when neither is.
  const primaryHex = feeling?.color_hex ?? outward?.color_hex ?? NEUTRAL_HEX;
  const secondaryHex = balanced ? outward.color_hex : null;

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
        onPick={(id) => save({ ...picks, primal: id, lean: lean ?? 'none' })}
      />

      <p className="strength-ask">
        {text(
          'gift_strength_others_question',
          'Does what you do to other people give you strength'
        )}
      </p>
      <div className="strength-row">
        {LEANS.map(({ lean: choice, key, fallback }) => (
          <button
            key={choice}
            type="button"
            aria-pressed={lean === choice}
            onClick={() => chooseLean(choice)}
          >
            {text(key, fallback)}
          </button>
        ))}
      </div>

      {chosenSide && (
        <>
          <p className="strength-ask">
            {text('gift_strength_outward_question', 'Which of these gives you strength')}
          </p>
          <ResonanceCards
            label={text('gift_strength_outward_question', 'Which of these gives you strength')}
            resonances={sideCards(chosenSide)}
            picked={outward?.id ?? null}
            onPick={chooseOutward}
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
            primaryHex={primaryHex}
            secondaryHex={secondaryHex}
            secondShare={outwardPoints / budget}
          />
          {auraName && <p className="strength-named">{auraName}</p>}
          {said && <p className="strength-said">{said}</p>}
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
            value={balanced ? outwardPoints : 1}
            disabled={!balanced}
            aria-describedby={pointsId}
            onChange={(event) =>
              save({ ...picks, primalPoints: budget - Number(event.target.value) })
            }
          />
          <div className="strength-pts" id={pointsId}>
            {pointsLine}
          </div>
          {neither && (
            <p className="strength-skipped">
              {text(
                'gift_strength_skipped',
                'With no second pick there is nothing to balance. All {points} points go to the feeling.'
              ).replace('{points}', String(budget))}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
