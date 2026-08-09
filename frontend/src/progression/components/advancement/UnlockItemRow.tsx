/**
 * UnlockItemRow — one purchasable row shared by BreakthroughsCard and
 * ClassUnlocksCard (#3045). Both cards read the same discriminated
 * `ProgressionUnlockItem` list (GET /api/progression/unlocks/) filtered by
 * `unlock_type`, so the row rendering (cost, "cost unset" marker, buy button)
 * is identical between them — only the buy-kwargs and the extra descriptive
 * line differ per card.
 *
 * "Cost unset" marker (#3045 spec decision 3): `xp_cost === 0` is the
 * server-side sentinel for "no ClassXPCost/TraitXPCost row authored" — see
 * `ClassLevelUnlock.get_xp_cost_for_character` / `TraitRatingUnlock
 * .get_xp_cost_for_character` (both fall back to 0 with the same comment).
 * The UI must never invent a number here — it renders whatever cost exists
 * and marks a 0-cost row honestly, staff-visible styling only.
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { ProgressionUnlockItem } from '@/progression/types';

interface UnlockItemRowProps {
  item: ProgressionUnlockItem;
  extraLine?: string | null;
  onBuy: () => void;
  buying: boolean;
}

export function UnlockItemRow({ item, extraLine, onBuy, buying }: UnlockItemRowProps) {
  const costUnset = item.requirements_met && item.xp_cost === 0;
  const canBuy = item.requirements_met && !buying;

  return (
    <div
      className="flex items-start justify-between gap-3 rounded-lg border p-3"
      data-testid="unlock-item-row"
    >
      <div className="min-w-0 space-y-0.5">
        <div className="font-medium">{item.display_name}</div>
        {extraLine && <div className="text-sm text-muted-foreground">{extraLine}</div>}
        {item.locked_reason && (
          <div className="text-sm text-destructive" data-testid="unlock-locked-reason">
            {item.locked_reason}
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        {costUnset ? (
          <Badge variant="outline" data-testid="unlock-cost-unset">
            Cost unset (staff)
          </Badge>
        ) : (
          <span className="text-sm font-medium tabular-nums">{item.xp_cost} XP</span>
        )}
        <Button size="sm" disabled={!canBuy} onClick={onBuy} data-testid="unlock-buy-button">
          {buying ? 'Buying…' : 'Buy'}
        </Button>
      </div>
    </div>
  );
}
