/**
 * RallyResonancePick - "Remind her of": the ally's resonances a Rally may name (#5124, demo
 * Screen 3). The rallier sees names only, never amounts and never whether one is kindled.
 * Choosing none leaves a plain Rally; choosing the chosen one again clears it.
 */

import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';

type RallyResonanceChoice = components['schemas']['RallyResonanceChoice'];

export interface RallyResonancePickProps {
  allyName: string;
  resonances: RallyResonanceChoice[];
  /** The chosen resonance id as a string, or '' for none. */
  selectedId: string;
  onSelect: (id: string) => void;
  disabled?: boolean;
}

export function RallyResonancePick({
  allyName,
  resonances,
  selectedId,
  onSelect,
  disabled = false,
}: RallyResonancePickProps) {
  const chosen = resonances.find((r) => String(r.id) === selectedId);
  return (
    <div className="space-y-1" data-testid="rally-resonance-pick">
      <p className="text-xs text-muted-foreground">
        {allyName ? `Remind ${allyName} of` : 'Remind them of'}
      </p>
      <div className="flex flex-wrap gap-1">
        {resonances.map((resonance) => {
          const on = String(resonance.id) === selectedId;
          return (
            <button
              key={resonance.id}
              type="button"
              disabled={disabled}
              aria-pressed={on}
              data-testid={`rally-resonance-${resonance.id}`}
              onClick={() => onSelect(on ? '' : String(resonance.id))}
              className={cn(
                'rounded-full border px-2 py-0.5 text-xs transition-colors',
                'disabled:cursor-not-allowed disabled:opacity-50',
                on ? 'border-primary bg-primary/10 font-medium' : 'border-border hover:bg-muted/50'
              )}
            >
              {resonance.name}
            </button>
          );
        })}
      </div>
      {chosen && (
        <p className="text-xs text-muted-foreground" data-testid="rally-resonance-note">
          If {chosen.name} is not kindled for them yet, your Rally kindles it until the end of the
          fight.
        </p>
      )}
    </div>
  );
}
