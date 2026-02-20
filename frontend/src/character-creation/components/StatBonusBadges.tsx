/**
 * Shared stat bonus badge display.
 *
 * Renders a Record<string, number> as colored badges (green for positive,
 * red for negative). Used by species cards, detail panels, and anywhere
 * stat bonuses need to be shown consistently.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { TrendingUp } from 'lucide-react';

interface StatBonusBadgesProps {
  /** Stat name → bonus value (e.g. { strength: 10, dexterity: -5 }) */
  statBonuses: Record<string, number>;
  /** Show "Stat Bonuses" header with icon. Default: false */
  showHeader?: boolean;
}

export function StatBonusBadges({ statBonuses, showHeader = false }: StatBonusBadgesProps) {
  const bonuses = Object.entries(statBonuses)
    .filter(([, value]) => value !== 0)
    .map(([stat, value]) => ({
      stat: stat.charAt(0).toUpperCase() + stat.slice(1),
      value,
    }));

  if (bonuses.length === 0) return null;

  return (
    <div>
      {showHeader && (
        <div className="mb-2 flex items-center gap-2 text-sm font-medium">
          <TrendingUp className="h-4 w-4 text-green-500" />
          <span>Stat Bonuses</span>
        </div>
      )}
      <div className="flex flex-wrap gap-1">
        {bonuses.map(({ stat, value }) => (
          <Badge
            key={stat}
            variant="outline"
            className={cn(
              'text-xs',
              value > 0 && 'border-green-500/50 bg-green-500/10 text-green-700',
              value < 0 && 'border-red-500/50 bg-red-500/10 text-red-700'
            )}
          >
            {stat} {value > 0 ? '+' : ''}
            {value}
          </Badge>
        ))}
      </div>
    </div>
  );
}
