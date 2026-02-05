/**
 * Free Points Widget
 *
 * Displays remaining free points to allocate in the Attributes stage.
 * Shows a visual pip indicator for points spent vs remaining.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface FreePointsWidgetProps {
  freePoints: number; // Remaining points (can be negative if over budget)
  maxPoints?: number; // Total free points available (default 5)
}

export function FreePointsWidget({ freePoints, maxPoints = 5 }: FreePointsWidgetProps) {
  const spentPoints = maxPoints - freePoints;
  const isOverBudget = freePoints < 0;
  const isComplete = freePoints === 0;

  // Generate pip indicators
  const pips = Array.from({ length: maxPoints }, (_, i) => {
    const isSpent = i < spentPoints;
    return (
      <span
        key={i}
        className={cn('text-lg', isSpent ? 'text-primary' : 'text-muted-foreground/40')}
        aria-hidden="true"
      >
        {isSpent ? '●' : '○'}
      </span>
    );
  });

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-center text-base">Free Points</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div
          className={cn(
            'text-center text-4xl font-bold',
            isOverBudget && 'text-red-600',
            isComplete && 'text-foreground',
            !isOverBudget && !isComplete && 'text-green-600'
          )}
          aria-label={`${freePoints} free points remaining`}
        >
          {freePoints}
        </div>
        <div
          className="flex justify-center gap-1"
          role="img"
          aria-label={`${spentPoints} of ${maxPoints} points spent`}
        >
          {pips}
        </div>
        {isOverBudget && (
          <p className="text-center text-sm text-red-600">Over budget by {Math.abs(freePoints)}</p>
        )}
      </CardContent>
    </Card>
  );
}
