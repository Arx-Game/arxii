/**
 * ReachRow (#5308, #5327): the optional "Reaching for" row of a pose and of a journal entry.
 * Switching it on offers every resonance, in her aura or not, and shows the chosen one's description.
 * Under it, "Pointing at" lists the acts her character took and has not marked, each with its
 * age and the resonance the situation suggested (or "No resonance suggested."). Pointing at an
 * act makes the writing a mark that pays when it is posted; on a pose, "Nothing" leaves a bare
 * reach that another player has to endorse. A journal entry has no "Nothing" choice, so its act
 * is required. In an ephemeral scene, which stores nothing, the act list gives way to a warning.
 *
 * Wire contract: `GET /api/magic/resonances/` and `GET /api/magic/recorded-acts/`; the request
 * fields come from `reachFields` in `reach.ts`.
 */

import { cn } from '@/lib/utils';
import { formatRelativeTime } from '@/lib/relativeTime';
import { chooseAct, chooseReach, toggleReach, type ReachDraft } from '@/magic/reach';
import { useRecordedActs, useResonanceCatalog } from '@/magic/queries';
import type { RecordedAct } from '@/magic/types';

interface Props {
  /** CharacterSheet pk of the writer; null while unknown, which leaves no act to point at. */
  characterSheetId: number | null;
  value: ReachDraft;
  onChange: (value: ReachDraft) => void;
  /** A journal entry: an act must be chosen, and there is no "Nothing" choice. */
  actRequired?: boolean;
  /** The scene stores nothing, so a mark there pays nothing. */
  ephemeral?: boolean;
  className?: string;
}

/** The line under an act: the suggestion for the chosen resonance, else the strongest one. */
function suggestionLine(act: RecordedAct, resonanceId: number | null): string {
  const suggestion =
    act.suggestions.find((row) => row.resonance_id === resonanceId) ?? act.suggestions[0];
  if (!suggestion) return 'No resonance suggested.';
  return `Suggested: ${suggestion.resonance_name}. ${suggestion.reason}`;
}

interface ActChoiceProps {
  testId: string;
  picked: boolean;
  onPick: () => void;
  children: React.ReactNode;
}

function ActChoice({ testId, picked, onPick, children }: ActChoiceProps) {
  return (
    <label
      className={cn(
        'flex cursor-pointer items-start gap-2 rounded-md border px-2.5 py-1.5',
        picked ? 'border-foreground bg-foreground/5' : 'border-border'
      )}
    >
      <input
        type="radio"
        name="reach-act"
        checked={picked}
        onChange={onPick}
        data-testid={testId}
        className="mt-1"
      />
      <span className="flex min-w-0 flex-col">{children}</span>
    </label>
  );
}

export function ReachRow({
  characterSheetId,
  value,
  onChange,
  actRequired = false,
  ephemeral = false,
  className,
}: Props) {
  const { data: catalog = [] } = useResonanceCatalog();
  const choosing = value.on && value.resonanceId !== null && !ephemeral;
  const { data: acts = [] } = useRecordedActs(characterSheetId, choosing);
  if (catalog.length === 0) return null;

  const chosen = catalog.find((resonance) => resonance.id === value.resonanceId);

  return (
    <div
      className={cn('space-y-2 rounded border border-border px-3 py-2', className)}
      data-testid="reach-row"
    >
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-pressed={value.on}
          onClick={() => onChange(toggleReach(value))}
          data-testid="reach-toggle"
          className={cn(
            'min-h-8 cursor-pointer rounded-full border px-3 py-1 text-xs',
            value.on
              ? 'border-foreground bg-foreground text-background'
              : 'border-border bg-transparent text-foreground hover:bg-accent'
          )}
        >
          Reaching for
        </button>
        {value.on && (
          <select
            aria-label="Resonance"
            value={value.resonanceId ?? ''}
            onChange={(event) =>
              onChange(chooseReach(value, event.target.value ? Number(event.target.value) : null))
            }
            data-testid="reach-select"
            className="min-h-8 rounded border border-border bg-background px-2 text-sm"
          >
            <option value="">Choose</option>
            {catalog.map((resonance) => (
              <option key={resonance.id} value={resonance.id}>
                {resonance.name}
              </option>
            ))}
          </select>
        )}
      </div>
      {value.on && chosen?.description && (
        <p className="text-xs text-muted-foreground" data-testid="reach-help">
          {chosen.description}
        </p>
      )}
      {value.on && ephemeral && (
        <p className="text-xs text-amber-700 dark:text-amber-400" data-testid="reach-ephemeral">
          This scene is ephemeral and stores nothing, so a mark here pays nothing. Mark the act
          later, in a pose in another scene or from a journal entry.
        </p>
      )}
      {choosing && (
        <fieldset className="space-y-1.5" data-testid="reach-acts">
          <legend className="text-sm font-semibold">
            {actRequired ? 'Pointing at (required)' : 'Pointing at'}
          </legend>
          {acts.map((act) => (
            <ActChoice
              key={act.id}
              testId={`reach-act-${act.id}`}
              picked={value.actId === act.id}
              onPick={() => onChange(chooseAct(value, act.id))}
            >
              <span className="text-sm font-medium">
                {act.label}{' '}
                <span className="text-xs font-normal text-muted-foreground">
                  {formatRelativeTime(act.created_at)}
                </span>
              </span>
              <span className="text-xs text-muted-foreground">
                {suggestionLine(act, value.resonanceId)}
              </span>
            </ActChoice>
          ))}
          {!actRequired && (
            <ActChoice
              testId="reach-act-none"
              picked={value.actId === null}
              onPick={() => onChange(chooseAct(value, null))}
            >
              <span className="text-sm font-medium">Nothing: another player has to endorse it</span>
            </ActChoice>
          )}
          {actRequired && acts.length === 0 && (
            <p className="text-xs text-muted-foreground" data-testid="reach-no-acts">
              You have no acts to point at.
            </p>
          )}
        </fieldset>
      )}
    </div>
  );
}
