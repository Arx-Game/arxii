/**
 * MagicTrainingBlock (#4659): what the chosen Tradition taught the character, spent on
 * Magic skills. The body of the Gift stage's own training funnel step, which carries the
 * "What <Tradition> taught you" heading (`trainingHeading`).
 *
 * Reads `draft.magic_training`: one breakdown line per (distinction, rank) that feeds the
 * pool ("Tradition Training, rank 1"; a one-rank distinction is just its name, "Studious",
 * per the server's `show_rank`), a "Fits:" line for each teaching-fit bonus, the
 * total, then a ledger that must reach exactly 0 (under- and overspending are both
 * flagged) and one `StatRow` per Magic skill, stepping by the server's `step` (the
 * active budget's points per tier). Each step writes the whole
 * `draft_data.magic_skills` map (the draft PATCH merges `draft_data` at the top level).
 * Renders nothing for a draft with no training and nothing allocated.
 */

import type { ReactNode } from 'react';
import { InstrumentFrame, StatRow } from '../../folio';
import { useCGExplanations, useUpdateDraft } from '../../queries';
import type {
  CGExplanations,
  CharacterDraft,
  MagicTrainingSkill,
  MagicTrainingSource,
} from '../../types';
import { hasMagicTraining } from './magicTraining';

interface MagicTrainingBlockProps {
  draft: CharacterDraft;
}

function increaseTitleFor(
  atCap: boolean,
  max: number,
  copy: CGExplanations | undefined
): string | undefined {
  if (!atCap) return undefined;
  return (copy?.gift_training_at_cap ?? 'At {max}, the most it can be').replace(
    '{max}',
    String(max)
  );
}

function ledgerRight(over: number, remaining: number, copy: CGExplanations | undefined): ReactNode {
  if (over > 0) {
    return (
      <>
        {copy?.gift_training_over ?? 'Over by'} <b>{over}</b>
      </>
    );
  }
  return (
    <>
      {copy?.gift_training_remaining ?? 'Remaining'} <b>{remaining}</b>
    </>
  );
}

export function MagicTrainingBlock({ draft }: MagicTrainingBlockProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const training = draft.magic_training;

  if (!hasMagicTraining(training)) return null;

  const over = training.allocated - training.total;
  const remaining = Math.max(training.required_spend - training.allocated, 0);
  const fitLine = (name: string) =>
    (copy?.gift_training_fits ?? 'Fits: {name}').replace('{name}', name);
  const sourceLine = (source: MagicTrainingSource) =>
    source.show_rank
      ? (copy?.gift_training_source ?? '{name}, rank {rank}')
          .replace('{name}', source.name)
          .replace('{rank}', String(source.rank))
      : source.name;
  const step = training.step;

  const handleChange = (skill: MagicTrainingSkill, value: number) => {
    const allocation: Record<string, number> = {};
    for (const row of training.skills) {
      const next = row.id === skill.id ? value : row.value;
      if (next > 0) allocation[String(row.id)] = next;
    }
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { magic_skills: allocation } },
    });
  };

  return (
    <div>
      <div className="breakdown">
        {training.base_sources.map((source, index) => (
          <div key={`${index}-${source.name}-${source.rank}`}>
            <span>{sourceLine(source)}</span>
            <span>{index === 0 ? source.points : `+${source.points}`}</span>
          </div>
        ))}
        {training.gift_bonus > 0 && training.favored_gift_name && (
          <div>
            <span>{fitLine(training.favored_gift_name)}</span>
            <span>+{training.gift_bonus}</span>
          </div>
        )}
        {training.affinity_bonus > 0 && training.favored_affinity_name && (
          <div>
            <span>{fitLine(training.favored_affinity_name)}</span>
            <span>+{training.affinity_bonus}</span>
          </div>
        )}
        <div className="total">
          <span>{copy?.gift_training_total ?? 'Magical training'}</span>
          <span>{training.total}</span>
        </div>
      </div>
      <InstrumentFrame
        label={copy?.gift_training_skills ?? 'Magic skills'}
        ledger={{
          left: copy?.gift_training_spend ?? 'Spend all of it',
          right: ledgerRight(over, remaining, copy),
          over: over > 0 || remaining > 0,
        }}
      >
        {training.skills.map((skill) => {
          const atCap = skill.value >= skill.max;
          return (
            <StatRow
              key={skill.id}
              id={`lbl-magic-skill-${skill.id}`}
              name={skill.name}
              value={skill.value}
              max={skill.max}
              step={step}
              onChange={(value) => handleChange(skill, value)}
              canDecrease={skill.value > 0 && !updateDraft.isPending}
              canIncrease={
                !atCap && training.allocated + step <= training.total && !updateDraft.isPending
              }
              increaseTitle={increaseTitleFor(atCap, skill.max, copy)}
            />
          );
        })}
      </InstrumentFrame>
    </div>
  );
}
