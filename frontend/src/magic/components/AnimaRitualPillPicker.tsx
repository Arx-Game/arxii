/**
 * AnimaRitualPillPicker (#5280): one pick of the anima ritual's two resonances, drawn as a row
 * of pills. The outward pick also offers "None".
 */
import { useId } from 'react';
import type { AnimaRitualResonance } from '@/rituals/api';
import { affinityInkClass } from './affinityInk';

interface AnimaRitualPillPickerProps {
  label: string;
  /** What the pills are, shown under them in the editor. */
  hint?: string;
  resonances: readonly AnimaRitualResonance[];
  /** The chosen resonance; null selects "None", undefined selects nothing yet. */
  selectedId: number | null | undefined;
  onSelect: (resonanceId: number | null) => void;
  /** Adds a "None" pill that selects no resonance. */
  allowNone?: boolean;
  disabled?: boolean;
  testId: string;
  /**
   * A resonance the ritual carries that she no longer holds: shown selected and disabled while it
   * is the pick, gone once she picks another.
   */
  keptUnheld?: AnimaRitualResonance | null;
}

const PILL = 'rounded-full border px-3 py-1 text-sm transition-colors';

/** Selected pills take a current-colour border and bold type; unselected sit on the muted ground. */
function pillClass(selected: boolean, ink: string): string {
  return `${PILL} ${ink} ${
    selected
      ? 'border-current bg-background font-semibold'
      : 'border-input bg-muted hover:bg-accent'
  }`;
}

export function AnimaRitualPillPicker({
  label,
  hint,
  resonances,
  selectedId,
  onSelect,
  allowNone = false,
  disabled = false,
  testId,
  keptUnheld = null,
}: AnimaRitualPillPickerProps) {
  const labelId = useId();
  return (
    <div className="flex min-w-0 flex-1 basis-56 flex-col gap-1.5" data-testid={testId}>
      <span id={labelId} className="text-sm font-medium">
        {label}
      </span>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {keptUnheld &&
          selectedId === keptUnheld.id &&
          !resonances.some((resonance) => resonance.id === keptUnheld.id) && (
            <button
              type="button"
              disabled
              aria-pressed={selectedId === keptUnheld.id}
              className={pillClass(
                selectedId === keptUnheld.id,
                affinityInkClass(keptUnheld.affinity_name)
              )}
            >
              {keptUnheld.name}
            </button>
          )}
        {resonances.map((resonance) => (
          <button
            key={resonance.id}
            type="button"
            disabled={disabled}
            aria-pressed={selectedId === resonance.id}
            onClick={() => onSelect(resonance.id)}
            className={pillClass(
              selectedId === resonance.id,
              affinityInkClass(resonance.affinity_name)
            )}
          >
            {resonance.name}
          </button>
        ))}
        {allowNone && (
          <button
            type="button"
            disabled={disabled}
            aria-pressed={selectedId === null}
            onClick={() => onSelect(null)}
            className={pillClass(selectedId === null, '')}
          >
            None
          </button>
        )}
      </div>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}
