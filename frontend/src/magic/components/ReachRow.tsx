/**
 * ReachRow (#5308): the optional "Reaching for" row of a pose. Switching it on offers every
 * resonance, held or not; an endorsement of the pose then pays the one chosen. Renders nothing
 * until the catalog has loaded.
 *
 * Wire contract: `GET /api/magic/resonances/`; the request field comes from `reachFields` in
 * `reach.ts`.
 */

import { cn } from '@/lib/utils';
import { chooseReach, toggleReach, type ReachDraft } from '@/magic/reach';
import { useResonanceCatalog } from '@/magic/queries';

interface Props {
  value: ReachDraft;
  onChange: (value: ReachDraft) => void;
  className?: string;
}

export function ReachRow({ value, onChange, className }: Props) {
  const { data: catalog = [] } = useResonanceCatalog();
  if (catalog.length === 0) return null;

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
    </div>
  );
}
