/**
 * ManifestPickerPanel (#4341): the technique picker. For each manifesting technique the
 * character knows, the options it can bring into a fight as buttons; the chosen one is
 * primary, one whose bond does not hold is disabled with the reason. Mounted in
 * SpellbookTab own-view, below MotifStylePanel. Renders nothing for a character with no
 * manifesting technique.
 *
 * Wire contract: GET /api/magic/manifest-choices/ (ManifestChoiceViewSet) reads; the
 * `manifest_set` action dispatch writes (src/actions/definitions/manifest.py).
 */

import { Button } from '@/components/ui/button';
import { useManifestChoices, useSetManifestChoice } from '@/magic/queries';
import type { ManifestChoice } from '@/magic/types';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the acting character. */
  characterSheetId: number;
}

function TechniqueBlock({
  choice,
  onChoose,
  pending,
}: {
  choice: ManifestChoice;
  onChoose: (techniqueId: number, optionId: number) => void;
  pending: boolean;
}) {
  return (
    <div
      className="space-y-2 rounded-md border p-3"
      data-testid={`manifest-technique-${choice.technique_id}`}
    >
      <p className="text-sm font-medium">Technique: {choice.technique_name}</p>
      <p className="text-sm text-muted-foreground">Brings into a fight:</p>
      <div className="flex flex-wrap gap-2">
        {choice.options.map((option) => {
          const chosen = choice.chosen_option_id === option.option_id;
          return (
            <Button
              key={option.option_id}
              type="button"
              size="sm"
              variant={chosen ? 'default' : 'outline'}
              aria-pressed={chosen}
              disabled={!option.available || pending}
              onClick={() => onChoose(choice.technique_id, option.option_id)}
              data-testid={`manifest-option-${option.option_id}`}
            >
              {option.available ? option.label : `${option.label} (${option.reason})`}
            </Button>
          );
        })}
      </div>
    </div>
  );
}

export function ManifestPickerPanel({ characterSheetId }: Props) {
  const { data: choices = [] } = useManifestChoices(characterSheetId);
  const setChoice = useSetManifestChoice(characterSheetId);

  if (choices.length === 0) return null;

  return (
    <div className="refsheet-stack-wide" data-testid="manifest-picker-panel">
      {choices.map((choice) => (
        <TechniqueBlock
          key={choice.technique_id}
          choice={choice}
          pending={setChoice.isPending}
          onChoose={(techniqueId, optionId) => setChoice.mutate({ techniqueId, optionId })}
        />
      ))}
      <p className="text-xs text-muted-foreground">
        Only options whose bond holds can be chosen; the others show why not.
      </p>
      {setChoice.isError ? (
        <p role="alert" className="text-sm font-medium text-red-500" data-testid="manifest-error">
          {setChoice.error?.message}
        </p>
      ) : null}
    </div>
  );
}
