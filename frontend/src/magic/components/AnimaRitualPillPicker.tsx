/**
 * AnimaRitualPillPicker (#5280): one pick of the anima ritual's two resonances, drawn as a row
 * of pills. The outward pick also offers "None".
 */
import { useId } from 'react';
import type { AnimaRitualResonance } from '@/rituals/api';
import { pillClass } from './pillClass';

interface AnimaRitualPillPickerProps {
  label: string;
  /** What the pills are, shown under them in the editor. */
  hint?: string;
  resonances: readonly AnimaRitualResonance[];
  selectedId: number | null;
  onSelect: (resonanceId: number | null) => void;
  /** Adds a "None" pill that selects no resonance. */
  allowNone?: boolean;
  disabled?: boolean;
  testId: string;
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
}: AnimaRitualPillPickerProps) {
  const labelId = useId();
  return (
    <div className="flex min-w-0 flex-1 basis-56 flex-col gap-1.5" data-testid={testId}>
      <span id={labelId} className="text-sm font-medium">
        {label}
      </span>
      <div role="group" aria-labelledby={labelId} className="flex flex-wrap gap-2">
        {resonances.map((resonance) => (
          <button
            key={resonance.id}
            type="button"
            disabled={disabled}
            aria-pressed={selectedId === resonance.id}
            onClick={() => onSelect(resonance.id)}
            className={pillClass(selectedId === resonance.id)}
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
            className={pillClass(selectedId === null)}
          >
            None
          </button>
        )}
      </div>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  );
}
