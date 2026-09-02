/**
 * ConsequencePoolPicker (#3562) - pick a ConsequencePool (or none) for one
 * of a beat's three outcome slots (success/failure/expired), with a preview
 * of the selected pool's resolved entries underneath.
 *
 * Three of these mount side by side in `BeatFormDialog`'s Consequences
 * section, one per outcome.
 */

import { useId } from 'react';
import { Label } from '@/components/ui/label';
import { useBeatConsequencePools, useConsequencePoolDetail } from '../queries';

interface ConsequencePoolPickerProps {
  value: number | null;
  onChange: (value: number | null) => void;
  label: string;
  disabled?: boolean;
}

export function ConsequencePoolPicker({
  value,
  onChange,
  label,
  disabled,
}: ConsequencePoolPickerProps) {
  const id = useId();
  const { data: pools = [] } = useBeatConsequencePools();
  const { data: detail } = useConsequencePoolDetail(value ?? -1);

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <select
        id={id}
        value={value != null ? String(value) : ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
        disabled={disabled}
        className="w-full rounded-md border bg-background px-3 py-2 text-sm"
      >
        <option value="">None</option>
        {pools.map((pool) => (
          <option key={pool.id} value={pool.id}>
            {pool.name}
          </option>
        ))}
      </select>
      {value != null && detail && (
        <ul
          className="space-y-1 rounded-md border bg-muted/30 p-2 text-xs"
          data-testid={`consequence-pool-entries-${value}`}
        >
          {detail.entries.length === 0 && (
            <li className="text-muted-foreground">This pool has no entries.</li>
          )}
          {detail.entries.map((entry) => (
            <li key={entry.consequence_id}>
              <span className="font-medium text-foreground">{entry.name}</span>
              {entry.outcome_tier && (
                <span className="text-muted-foreground">
                  {' - '}
                  {entry.outcome_tier.name} (success level {entry.outcome_tier.success_level})
                </span>
              )}
              {entry.effect_types.length > 0 && (
                <span className="text-muted-foreground">
                  {' - '}
                  {entry.effect_types.join(', ')}
                </span>
              )}
              {entry.character_loss && (
                <span className="text-destructive"> - may remove the character</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
