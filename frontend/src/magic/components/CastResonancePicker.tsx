/**
 * CastResonancePicker (#5231, Screen 4 of the approved demo): the resonances a cast may be
 * worked in, one row each, on the scene cast panel and the combat cast declaration.
 *
 * A row carries the resonance's colour and name, "your usual" on the default, the kindled
 * word and its reason when the resonance is kindled, "Stronger here than <the usual one>."
 * on the single option the server marked stronger, and "Adds corruption." on one that adds
 * it. Choosing nothing works the default, so the picker never blocks a cast. With fewer than
 * two options there is nothing to choose and nothing is drawn.
 */
import { useId } from 'react';
import { cn } from '@/lib/utils';
import type { CastResonanceOption } from '../types';

interface CastResonancePickerProps {
  options: CastResonanceOption[];
  /** The resonance the player picked; null until they pick, which means the default. */
  selectedId: number | null;
  onSelect: (resonanceId: number) => void;
  disabled?: boolean;
}

export function CastResonancePicker({
  options,
  selectedId,
  onSelect,
  disabled = false,
}: CastResonancePickerProps) {
  const labelId = useId();
  if (options.length < 2) return null;

  const defaultOption = options.find((option) => option.is_default);
  const activeId = selectedId ?? defaultOption?.resonance_id ?? null;

  return (
    <div className="space-y-1.5" data-testid="cast-resonance-picker">
      <p id={labelId} className="text-xs font-medium">
        Work it in:
      </p>
      <div aria-labelledby={labelId} role="group" className="space-y-1.5">
        {options.map((option) => {
          const active = option.resonance_id === activeId;
          return (
            <button
              key={option.resonance_id}
              type="button"
              disabled={disabled}
              aria-pressed={active}
              onClick={() => onSelect(option.resonance_id)}
              data-testid={`cast-resonance-${option.resonance_id}`}
              className={cn(
                'grid w-full grid-cols-[1rem_minmax(0,1fr)] gap-x-2 gap-y-0.5 rounded-md border p-2 text-left text-xs disabled:cursor-not-allowed disabled:opacity-60',
                active ? 'border-primary ring-1 ring-inset ring-primary' : 'border-border'
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  'mt-0.5 inline-block h-3 w-3 rounded-full border',
                  active ? 'border-primary bg-primary' : 'border-muted-foreground'
                )}
              />
              <span className="flex flex-wrap items-center gap-x-2">
                <span
                  aria-hidden="true"
                  data-testid={`cast-resonance-swatch-${option.resonance_id}`}
                  className="inline-block h-3 w-3 rounded-full border"
                  style={{ backgroundColor: option.color_hex }}
                />
                <b className="text-sm">{option.name}</b>
                {option.is_default && <span className="text-muted-foreground">your usual</span>}
                {option.kindled_strength && (
                  <span
                    className="border border-current px-1.5 py-0.5 text-[11px] font-semibold text-primary"
                    data-testid={`cast-resonance-kindled-${option.resonance_id}`}
                  >
                    Kindled, {option.kindled_strength}
                  </span>
                )}
              </span>
              {option.reasons.map((reason) => (
                <span key={reason} className="col-start-2 text-muted-foreground">
                  {reason}
                </span>
              ))}
              {(option.stronger || option.adds_corruption) && (
                <span className="col-start-2 text-muted-foreground">
                  {option.stronger && (
                    <b className="font-semibold text-foreground">
                      Stronger here than {defaultOption?.name}.
                    </b>
                  )}
                  {option.stronger && option.adds_corruption && ' '}
                  {option.adds_corruption && 'Adds corruption.'}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
