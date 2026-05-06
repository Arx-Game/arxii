import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';

interface HollowBarProps {
  current: number;
  max: number;
}

function getHollowColor(percentage: number): string {
  if (percentage < 50) {
    return 'bg-green-500';
  }
  if (percentage < 80) {
    return 'bg-amber-500';
  }
  return 'bg-red-500';
}

export function HollowBar({ current, max }: HollowBarProps) {
  // Calculate percentage, capped at 100
  const percentage = max === 0 ? 0 : Math.min(100, (current / max) * 100);

  const colorClass = getHollowColor(percentage);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">Hollow</span>
        <span className="tabular-nums text-muted-foreground">
          {current}/{max}
        </span>
      </div>
      <Progress
        value={percentage}
        className="h-2"
        indicatorClassName={cn(colorClass, 'transition-all')}
      />
    </div>
  );
}
