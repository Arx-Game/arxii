import { Progress } from '@/components/ui/progress';

import type { ManagerBuilding } from '../types';

/** The space-budget meter every builder mutation is measured against. */
export function BudgetMeter({ building }: { building: ManagerBuilding }) {
  const percent =
    building.space_budget > 0
      ? Math.min(100, Math.round((building.space_used / building.space_budget) * 100))
      : 0;
  return (
    <div className="flex items-center gap-3" data-testid="budget-meter">
      <Progress value={percent} className="w-40" />
      <span className="whitespace-nowrap text-sm text-muted-foreground">
        Space: {building.space_used}/{building.space_budget} ({building.space_remaining} free)
      </span>
    </div>
  );
}
