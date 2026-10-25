/**
 * MagicTrainingBlock (#4659): what the chosen Tradition taught the character, spent on
 * Magic skills.
 *
 * Reads `draft.magic_training`: one breakdown line per distinction that feeds the pool,
 * a "Fits:" line for each teaching-fit bonus, the total, then a ledger that must reach
 * exactly 0 and one `StatRow` per Magic skill. Each step writes the whole
 * `draft_data.magic_skills` map (the draft PATCH merges `draft_data` at the top level).
 * Renders nothing for a draft with no training and nothing allocated.
 */

import { InstrumentFrame, StatRow } from '../../folio';
import { useCGExplanations, useUpdateDraft } from '../../queries';
import type { CharacterDraft, MagicTrainingSkill } from '../../types';

/** Magic skills rise in the same steps of ten as every other skill. */
const STEP = 10;

interface MagicTrainingBlockProps {
  draft: CharacterDraft;
}

function increaseTitleFor(atCap: boolean, max: number): string | undefined {
  return atCap ? `At ${max}, the most it can be` : undefined;
}

export function MagicTrainingBlock({ draft }: MagicTrainingBlockProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const training = draft.magic_training;

  if (!training || (training.total === 0 && training.allocated === 0)) return null;

  const traditionName = draft.selected_tradition?.name ?? '';
  const over = training.allocated - training.total;
  const remaining = training.required_spend - training.allocated;
  const fitLine = (name: string) =>
    (copy?.gift_training_fits ?? 'Fits: {name}').replace('{name}', name);

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
    <section aria-labelledby="magic-training-heading">
      <h3 className="section-h" id="magic-training-heading">
        {(copy?.gift_training_heading ?? 'What {tradition} taught you').replace(
          '{tradition}',
          traditionName
        )}
      </h3>
      <div className="breakdown">
        {training.base_sources.map((source, index) => (
          <div key={source.name}>
            <span>{source.name}</span>
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
          right:
            over > 0 ? (
              <>
                {copy?.gift_training_over ?? 'Over by'} <b>{over}</b>
              </>
            ) : (
              <>
                {copy?.gift_training_remaining ?? 'Remaining'} <b>{Math.max(remaining, 0)}</b>
              </>
            ),
          over: over > 0 || remaining < 0,
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
              step={STEP}
              onChange={(value) => handleChange(skill, value)}
              canDecrease={skill.value > 0 && !updateDraft.isPending}
              canIncrease={
                !atCap && training.allocated + STEP <= training.total && !updateDraft.isPending
              }
              increaseTitle={increaseTitleFor(atCap, skill.max)}
            />
          );
        })}
      </InstrumentFrame>
    </section>
  );
}
