/**
 * Lineage record (#3660): a compact ledger of what the Lineage chapter has
 * cost so far - the chosen Upbringing, each answered priced question, any
 * Distinctions those answers bundled for free, and the running CG tally.
 * Rendered at the end of LineageStage's content.
 */

import { useCGPointBudget } from '../../queries';
import {
  chosenGroupForSlot,
  choiceCost,
  isAnswered,
  questionInfluence,
  shownSlotIds,
  type CharacterDraft,
  type FamilyPath,
  type OriginTemplate,
} from '../../types';

interface Props {
  draft: CharacterDraft;
  template: OriginTemplate;
  path: FamilyPath | '';
}

function costLabel(cost: number): string {
  return cost === 0 ? 'Free' : `${cost} pts`;
}

export function LineageRecord({ draft, template, path }: Props) {
  const { data: cgBudget } = useCGPointBudget();
  const starting = cgBudget?.starting_points ?? 100;

  const shown = shownSlotIds(template, draft, path);
  const picks = draft.draft_data.origin_choices ?? {};

  const priced = template.slots
    .filter((slot) => shown.has(slot.id) && slot.choices.length > 0 && isAnswered(slot, draft))
    .map((slot) => {
      const choiceId = picks[String(slot.id)] ?? null;
      const choice = slot.choices.find((c) => c.id === choiceId);
      if (!choice) return null;
      const group = slot.kind === 'group' ? chosenGroupForSlot(slot, template, draft) : null;
      const influence = questionInfluence(slot, group, draft, path);
      const cost = choiceCost(choice, influence);
      const line = group ? `${choice.name} · ${group.name}` : choice.name;
      return { key: slot.id, line, cost };
    })
    .filter((row): row is { key: number; line: string; cost: number } => row !== null);

  return (
    <section
      className="space-y-1 rounded-md border p-3 text-sm text-muted-foreground"
      data-testid="lineage-record"
    >
      <p className="font-medium text-foreground">
        {`${template.name} · ${costLabel(template.cg_point_cost)}`}
      </p>
      {priced.map((row) => (
        <p key={row.key}>{`${row.line} · ${costLabel(row.cost)}`}</p>
      ))}
      {draft.bundled_distinctions.map((d) => (
        <p key={d.distinction_id}>{`${d.name} · bundled`}</p>
      ))}
      <p>{`CG points: ${draft.cg_points_spent} of ${starting}`}</p>
    </section>
  );
}
