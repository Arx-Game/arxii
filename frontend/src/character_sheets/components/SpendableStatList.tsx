/**
 * Shared spend-a-point stat list for the Maturation (#2756) and Level Stat
 * Point (#3001) panels — one row per stat with a +1 button, capped per stage.
 */

import { Button } from '@/components/ui/button';

export interface SpendableStat {
  trait_id: number;
  name: string;
  value: number;
  at_cap: boolean;
}

interface SpendableStatListProps {
  stats: SpendableStat[];
  statCap: number | null;
  disabled: boolean;
  onSpend: (traitId: number) => void;
}

export function SpendableStatList({ stats, statCap, disabled, onSpend }: SpendableStatListProps) {
  return (
    <ul className="mt-2 space-y-1">
      {stats.map((stat) => (
        <li key={stat.trait_id} className="flex items-center justify-between gap-2">
          <span className="capitalize">
            {stat.name} ({stat.value}
            {statCap !== null && ` / ${statCap}`})
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={stat.at_cap || disabled}
            onClick={() => onSpend(stat.trait_id)}
          >
            +1
          </Button>
        </li>
      ))}
    </ul>
  );
}
