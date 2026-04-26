/**
 * Progress bar for AGGREGATE_THRESHOLD beats.
 * Shows current contribution total vs required_points.
 */

import { Progress } from '@/components/ui/progress';

interface AggregateProgressBarProps {
  current: number;
  required: number;
}

export function AggregateProgressBar({ current, required }: AggregateProgressBarProps) {
  const pct = required > 0 ? Math.min(100, Math.round((current / required) * 100)) : 0;

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>Progress</span>
        <span>
          {current} / {required}
        </span>
      </div>
      <Progress value={pct} className="h-2" />
    </div>
  );
}
