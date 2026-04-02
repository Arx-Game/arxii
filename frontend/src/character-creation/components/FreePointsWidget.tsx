/**
 * Points Budget Widget
 *
 * Displays remaining points to allocate in the Attributes stage.
 * Shows points remaining of total budget.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface FreePointsWidgetProps {
  pointsRemaining: number; // Remaining points (can be negative if over budget)
  budget: number; // Total stat point budget
}

export function FreePointsWidget({ pointsRemaining, budget }: FreePointsWidgetProps) {
  const pointsAllocated = budget - pointsRemaining;
  const isOverBudget = pointsRemaining < 0;
  const isComplete = pointsRemaining === 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-center text-base">Stat Points</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <div
          className={cn(
            'text-center text-4xl font-bold',
            isOverBudget && 'text-red-600',
            isComplete && 'text-foreground',
            !isOverBudget && !isComplete && 'text-green-600'
          )}
          aria-label={`${pointsRemaining} points remaining`}
        >
          {pointsRemaining}
        </div>
        <p className="text-center text-sm text-muted-foreground">
          {pointsAllocated} / {budget} allocated
        </p>
        {isOverBudget && (
          <p className="text-center text-sm text-red-600">
            Over budget by {Math.abs(pointsRemaining)}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
