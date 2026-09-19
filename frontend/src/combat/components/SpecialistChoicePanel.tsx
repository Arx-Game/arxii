import { useState } from 'react';
import { useResolvePendingSelection } from '../queries';
import type { EncounterDetail } from '../types';

export interface SpecialistChoicePanelProps {
  encounterId: number;
  selections?: EncounterDetail['pending_selections'];
}

/** Browser surface for deferred specialist choices such as Sage weakness reading. */
export function SpecialistChoicePanel({ encounterId, selections }: SpecialistChoicePanelProps) {
  const pending = (selections ?? []).filter((selection) => !selection.resolved);
  if (pending.length === 0) return null;
  return <PendingSelectionList encounterId={encounterId} selections={pending} />;
}

function PendingSelectionList({
  encounterId,
  selections,
}: {
  encounterId: number;
  selections: NonNullable<EncounterDetail['pending_selections']>;
}) {
  const [chosen, setChosen] = useState<Record<number, string>>({});
  const resolve = useResolvePendingSelection(encounterId);
  return (
    <section
      className="space-y-2 rounded-md border border-violet-500/50 bg-violet-950/20 p-3"
      data-testid="specialist-choice-panel"
    >
      <h3 className="text-xs font-semibold uppercase tracking-wide text-violet-200">
        Specialist choice
      </h3>
      {selections.map((selection) => (
        <div
          key={selection.id}
          className="space-y-2"
          data-testid={`specialist-selection-${selection.id}`}
        >
          <p className="text-xs text-foreground">Choose an option to continue.</p>
          <div className="grid gap-1">
            {selection.options.map((option) => (
              <button
                key={option.id}
                type="button"
                onClick={() => setChosen((old) => ({ ...old, [selection.id]: option.id }))}
                className={`rounded border px-2 py-1 text-left text-xs ${chosen[selection.id] === option.id ? 'border-violet-300 bg-violet-500/20' : 'border-border'}`}
                aria-pressed={chosen[selection.id] === option.id}
              >
                <span className="font-medium">{option.label}</span>
                {option.description && (
                  <span className="ml-1 text-muted-foreground">— {option.description}</span>
                )}
              </button>
            ))}
          </div>
          <button
            type="button"
            disabled={!chosen[selection.id] || resolve.isPending}
            onClick={() =>
              resolve.mutate({ selectionId: selection.id, optionId: chosen[selection.id] })
            }
            className="rounded bg-violet-600 px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {resolve.isPending ? 'Applying…' : 'Apply choice'}
          </button>
        </div>
      ))}
    </section>
  );
}
