/**
 * CG Points Budget Widget
 *
 * Displays current CG points budget with spent/remaining breakdown.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { Coins } from 'lucide-react';

interface CGPointsWidgetProps {
  starting: number;
  spent: number;
  remaining: number;
  className?: string;
}

export function CGPointsWidget({ starting, spent, remaining, className }: CGPointsWidgetProps) {
  const percentUsed = starting > 0 ? (spent / starting) * 100 : 0;
  const isOverBudget = remaining < 0;

  return (
    <Card className={cn('sticky top-4', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Coins className="h-5 w-5 text-amber-500" />
            <CardTitle className="text-base">CG Points Budget</CardTitle>
          </div>
          <div
            className={cn(
              'text-xl font-bold',
              isOverBudget && 'text-destructive',
              !isOverBudget && remaining <= 10 && 'text-amber-500',
              !isOverBudget && remaining > 10 && 'text-foreground'
            )}
          >
            {remaining}/{starting}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Progress value={percentUsed} className="h-2" />
        <div className="flex justify-between text-sm">
          <span className="text-muted-foreground">
            Spent: <span className="font-medium text-foreground">{spent}</span>
          </span>
          <span className={cn('font-medium', isOverBudget && 'text-destructive')}>
            {isOverBudget ? 'Over budget!' : `${remaining} remaining`}
          </span>
        </div>
        {isOverBudget && (
          <CardDescription className="text-destructive">
            You've exceeded your budget. Remove some selections before continuing.
          </CardDescription>
        )}
      </CardContent>
    </Card>
  );
}
