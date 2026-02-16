/**
 * CG Points Budget Widget
 *
 * Displays current CG points budget with spent/remaining breakdown.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import { Coins } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

function AnimatedNumber({ value, className }: { value: number; className?: string }) {
  const [displayValue, setDisplayValue] = useState(value);
  const [isAnimating, setIsAnimating] = useState(false);
  const prevValue = useRef(value);
  const animationIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (prevValue.current === value) return;

    // Cancel any existing animation before starting a new one
    if (animationIdRef.current !== null) {
      cancelAnimationFrame(animationIdRef.current);
    }

    setIsAnimating(true);
    const start = prevValue.current;
    const diff = value - start;
    const duration = Math.min(Math.abs(diff) * 50, 400);
    const startTime = performance.now();

    function animate(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayValue(Math.round(start + diff * eased));

      if (progress < 1) {
        animationIdRef.current = requestAnimationFrame(animate);
      } else {
        animationIdRef.current = null;
        setIsAnimating(false);
        prevValue.current = value;
      }
    }

    animationIdRef.current = requestAnimationFrame(animate);
    prevValue.current = value;

    return () => {
      if (animationIdRef.current !== null) {
        cancelAnimationFrame(animationIdRef.current);
      }
    };
  }, [value]);

  return (
    <span className={cn(className, isAnimating && 'scale-110 transition-transform')}>
      {displayValue}
    </span>
  );
}

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
          <div className="text-xl font-bold">
            <AnimatedNumber
              value={remaining}
              className={cn(
                isOverBudget && 'text-destructive',
                !isOverBudget && remaining <= 10 && 'text-amber-500',
                !isOverBudget && remaining > 10 && 'text-foreground'
              )}
            />
            /{starting}
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
