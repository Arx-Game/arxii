import { Badge } from '@/components/ui/badge';
import { StatBar } from '@/components/character/StatBar';
import { cn } from '@/lib/utils';
import type { FatiguePoolStatus, FatigueStatus, FatigueZone } from '../fatigueQueries';

const ZONE_COLORS: Record<FatigueZone, string> = {
  fresh: 'bg-green-500',
  strained: 'bg-yellow-500',
  tired: 'bg-orange-500',
  overexerted: 'bg-red-500',
  exhausted: 'bg-red-800',
};

const ZONE_BADGE_CLASSES: Record<FatigueZone, string> = {
  fresh: 'bg-green-100 text-green-800 border-green-300',
  strained: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  tired: 'bg-orange-100 text-orange-800 border-orange-300',
  overexerted: 'bg-red-100 text-red-800 border-red-300',
  exhausted: 'bg-red-200 text-red-900 border-red-400',
};

const POOL_LABELS: Record<string, string> = {
  physical: 'Physical',
  social: 'Social',
  mental: 'Mental',
};

function FatigueBar({ label, pool }: { label: string; pool: FatiguePoolStatus }) {
  // Invert percentage: 0% fatigue = full bar (fresh), 100% fatigue = empty bar (exhausted)
  const remainingPercent = Math.max(0, 100 - Math.min(100, pool.percentage));

  return (
    <StatBar
      label={label}
      valueText={`${pool.current}/${pool.capacity}`}
      percent={remainingPercent}
      fillClass={ZONE_COLORS[pool.zone]}
      badge={
        <Badge variant="outline" className={cn('text-xs capitalize', ZONE_BADGE_CLASSES[pool.zone])}>
          {pool.zone}
        </Badge>
      }
    />
  );
}

export function FatigueBars({ status }: { status: FatigueStatus }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Fatigue</span>
        {status.well_rested && (
          <Badge variant="secondary" className="border-blue-300 bg-blue-100 text-blue-800">
            Well Rested
          </Badge>
        )}
      </div>
      {(['physical', 'social', 'mental'] as const).map((pool) => (
        <FatigueBar key={pool} label={POOL_LABELS[pool]} pool={status[pool]} />
      ))}
    </div>
  );
}
