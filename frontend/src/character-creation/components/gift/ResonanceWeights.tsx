/**
 * ResonanceWeights (#5123, Screen 1 of the approved demo): the Gift stage's resonance step.
 * A new character spreads the creation points across the resonances that move them, and the
 * aura that spread makes is previewed beside it in words. Each row keeps its description
 * and codex line.
 */

import { AuraHalo } from '@/magic/components/AuraHalo';
import { CodexLine } from '../../folio';
import type { Resonance, ResonanceWeightPick } from '../../types';
import { placedPoints, weightOf, withWeight } from '../../resonanceWeights';

interface ResonanceWeightsProps {
  resonances: Resonance[];
  weights: ResonanceWeightPick[];
  /** The points to spread: the server's creation points, never a number kept here. */
  budget: number;
  onChange: (weights: ResonanceWeightPick[]) => void;
}

/** What the picks make of the aura: each affinity holds the points on its resonances. */
function auraShares(resonances: Resonance[], weights: ResonanceWeightPick[]) {
  const byAffinity = new Map<string, number>();
  for (const pick of weights) {
    const resonance = resonances.find((row) => row.id === pick.resonance_id);
    if (!resonance) continue;
    byAffinity.set(
      resonance.affinity_name,
      (byAffinity.get(resonance.affinity_name) ?? 0) + pick.weight
    );
  }
  return Array.from(byAffinity, ([name, percent]) => ({ name, percent }));
}

export function ResonanceWeights({ resonances, weights, budget, onChange }: ResonanceWeightsProps) {
  const placed = placedPoints(weights);
  const full = placed >= budget;
  const aura = auraShares(resonances, weights);

  return (
    <div className="resonance-weights">
      <div className="leaf-body">
        <p>
          Resonance is what powers your magic. It is the feeling that invigorates you, drives you or
          thrills you. For some it is a passion of their own: fury, wonder, delight. For some it is
          the joy of seeing someone helped. For some it is the pleasure of someone else's fear or
          suffering.
        </p>
        <p>
          Most people are moved by more than one thing. Choose what powers you, and how strongly.
        </p>
      </div>
      <p className="resonance-budget" aria-live="polite">
        {placed} of {budget} placed
      </p>
      <ul className="resonance-rows" aria-label="Resonances">
        {resonances.map((resonance) => {
          const weight = weightOf(weights, resonance.id);
          return (
            <li key={resonance.id} className="resonance-row">
              <div className="resonance-row-name">
                <span className="resonance-name">{resonance.name}</span>
                <span className="resonance-affinity">{resonance.affinity_name}</span>
              </div>
              <div className="resonance-stepper">
                {weight > 0 && (
                  <>
                    <button
                      type="button"
                      aria-label={`Less ${resonance.name}`}
                      onClick={() => onChange(withWeight(weights, resonance.id, weight - 1))}
                    >
                      -
                    </button>
                    <span
                      className="resonance-pips"
                      role="img"
                      aria-label={`${resonance.name}: ${weight} ${weight === 1 ? 'point' : 'points'}`}
                    >
                      {Array.from({ length: weight }, (_, index) => (
                        <span key={index} className="resonance-pip" />
                      ))}
                    </span>
                  </>
                )}
                <button
                  type="button"
                  aria-label={`More ${resonance.name}`}
                  disabled={full}
                  onClick={() => onChange(withWeight(weights, resonance.id, weight + 1))}
                >
                  +
                </button>
              </div>
              <div className="resonance-row-body">
                {resonance.description && <p>{resonance.description}</p>}
                <CodexLine entryId={resonance.codex_entry_id} name={resonance.name} />
              </div>
            </li>
          );
        })}
      </ul>
      {aura.length > 0 && (
        <AuraHalo shares={aura}>
          <span className="resonance-aura-label">Your aura</span>
        </AuraHalo>
      )}
    </div>
  );
}
