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
import type { Affinity, CGExplanations, Resonance, ResonanceWeightPick } from '../../types';
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
  /** The three affinities; each one's staff-written description sits with its cards. */
  affinities?: Affinity[];
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

/** The affinity's description, under the question for its cards; nothing while it is blank. */
function AffinityNote({ affinities, name }: { affinities: Affinity[]; name: string }) {
  const description = affinities.find((affinity) => affinity.name === name)?.description.trim();
  if (!description) return null;
  return (
    <p className="strength-affinity" data-testid="strength-affinity-description">
      {description}
    </p>
  );
}

/** "a Celestial", "an Abyssal": the side word with its article. */
function withArticle(affinity: string): string {
  return `${/^[AEIOU]/.test(affinity) ? 'an' : 'a'} ${affinity}`;
}

type Text = (key: string, fallback: string) => string;

/** The aura's caption and sentence: none before a feeling is chosen. */
function auraWords({
  hasFeeling,
  balanced,
  main,
  otherSide,
  text,
}: {
  hasFeeling: boolean;
  balanced: boolean;
  main: string;
  otherSide: string;
  text: Text;
}): { auraName: string | null; said: string | null } {
  if (balanced) {
    return {
      auraName: `${main}, with ${withArticle(otherSide)} side`,
      said:
        main === 'Primal'
          ? text(
              'gift_strength_aura_mostly_feeling',
              'Most of your strength comes from what you feel.'
            )
          : text(
              'gift_strength_aura_mostly_others',
              'Most of your strength comes from what you do to others.'
            ),
    };
  }
  if (hasFeeling) {
    return {
      auraName: 'Primal',
      said: text('gift_strength_aura_all_feeling', 'All your strength comes from what you feel.'),
    };
  }
  return { auraName: null, said: null };
}

/** The points under the slider: each pick with its share, or the one pick holding them all. */
function pointsLineFor({
  feeling,
  outward,
  balanced,
  neither,
  primalPoints,
  outwardPoints,
  budget,
}: {
  feeling: Resonance | undefined;
  outward: Resonance | undefined;
  balanced: boolean;
  neither: boolean;
  primalPoints: number;
  outwardPoints: number;
  budget: number;
}): string {
  if (balanced && feeling && outward) {
    return `${feeling.name} ${primalPoints} · ${outward.name} ${outwardPoints}`;
  }
  if (neither && feeling) return `${feeling.name} ${budget}`;
  const only = feeling ?? outward;
  return only ? `${only.name} ${budget}` : '';
}

export function StrengthStep({
  resonances,
  affinities = [],
  weights,
  budget,
  copy,
  onChange,
}: StrengthStepProps) {
  const sliderId = useId();
  const pointsId = useId();
  const picks = picksFromWeights(weights, resonances, budget);
  const text = (key: string, fallback: string) => copy?.[key] ?? fallback;

  const primalCards = resonances.filter((resonance) => resonance.affinity_name === 'Primal');
  const sideCards = (lean: 'give' | 'take') =>
    resonances.filter((resonance) => resonance.affinity_name === affinityOfLean(lean));
  const nameOf = (id: number | null) => resonances.find((resonance) => resonance.id === id);

  const save = (next: StrengthPicks) => onChange(weightsFromPicks(next, budget));

  // Her answer about other people is her own, in this visit. Until she gives one it reads the
  // saved list: the second pick's side, "Neither" for a feeling alone (she finished that way
  // before), nothing for an empty list. Once she acts in the step it is frozen at what she has
  // given, so picking a feeling never presses or changes it, and a side chosen before any card
  // is picked stays pressed though the saved list cannot hold it.
  const [answer, setAnswer] = useState<Lean | null | undefined>(undefined);
  const lean: Lean | null = answer !== undefined ? answer : picks.lean;

  const chooseLean = (next: Lean) => {
    setAnswer(next);
    if (next === 'none') {
      save({ ...picks, lean: next, outward: null, primalPoints: budget });
      return;
    }
    // A side gives her no card: she picks one herself. Only a second pick left over from the
    // other side is cleared, in one write.
    if (picks.outward != null && picks.lean !== next) {
      save({ ...picks, lean: next, outward: null, primalPoints: budget });
    }
  };

  const chooseFeeling = (id: number) => {
    setAnswer(lean);
    save({ ...picks, primal: id, lean: lean ?? 'none' });
  };

  // A feeling that held every point gives up a share to the second pick (the demo's 7 of 10).
  const chooseOutward = (id: number) => {
    const primalPoints = picks.outward == null ? defaultPrimalPoints(budget) : picks.primalPoints;
    setAnswer(lean);
    save({ ...picks, lean, outward: id, primalPoints });
  };

  const feeling = nameOf(picks.primal);
  const chosenSide = lean === 'give' || lean === 'take' ? lean : null;
  const outward = chosenSide && picks.lean === chosenSide ? nameOf(picks.outward) : undefined;
  // The balance exists once both picks do; before that the slider is off.
  const balanced = feeling != null && outward != null;
  const neither = lean === 'none' && feeling != null;
  const outwardPoints = balanced ? budget - picks.primalPoints : 0;
  const main = mainAffinityOf(picks, budget);
  const otherSide = main === 'Primal' && chosenSide ? affinityOfLean(chosenSide) : 'Primal';
  // No name and no sentence before a feeling is chosen: the aura claims nothing she has not.
  const { auraName, said } = auraWords({
    hasFeeling: feeling != null,
    balanced,
    main,
    otherSide,
    text,
  });
  const pointsLine = pointsLineFor({
    feeling,
    outward,
    balanced,
    neither,
    primalPoints: picks.primalPoints,
    outwardPoints,
    budget,
  });
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
      <AffinityNote affinities={affinities} name="Primal" />
      <ResonanceCards
        label={text('gift_strength_feeling_question', 'Which feeling gives you strength')}
        resonances={primalCards}
        picked={picks.primal}
        onPick={chooseFeeling}
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
          <AffinityNote affinities={affinities} name={affinityOfLean(chosenSide)} />
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
