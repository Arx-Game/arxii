/**
 * ClassUnlocksCard (#3045) — buy a class-level unlock (the XP-purchase gate
 * stacked alongside the Ritual of the Durance's authored requirements — see
 * "Multi-gate rule" in world/progression/CLAUDE.md).
 *
 * Reads `GET /api/progression/unlocks/?unlock_type=class_level` and purchases
 * through `POST /api/progression/unlocks/purchase/` — the same
 * `PurchaseUnlockAction` seam telnet's `progression unlock class=<id>` uses.
 */

import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useProgressionUnlocksQuery, usePurchaseUnlockMutation } from '@/progression/queries';
import { UnlockItemRow } from './UnlockItemRow';

export function ClassUnlocksCard() {
  const { data, isLoading, error } = useProgressionUnlocksQuery('class_level');
  const purchase = usePurchaseUnlockMutation();

  const items = data?.results ?? [];

  function handleBuy(classLevelUnlockId: number) {
    purchase.mutate(
      { unlock_type: 'class_level', class_level_unlock_id: classLevelUnlockId },
      {
        onSuccess: () => toast.success('Class-level unlock purchased.'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not purchase the unlock.'),
      }
    );
  }

  return (
    <Card data-testid="class-unlocks-card">
      <CardHeader>
        <CardTitle className="text-base">Class Unlocks</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Failed to load class unlocks.</p>}
        {!isLoading && !error && items.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="class-unlocks-empty">
            No class-level unlocks are available right now.
          </p>
        )}
        {items.map((item) => (
          <UnlockItemRow
            key={`class-level-${item.class_level_unlock_id}`}
            item={item}
            extraLine={
              item.class_name ? `${item.class_name} → level ${item.target_level}` : undefined
            }
            onBuy={() =>
              item.class_level_unlock_id !== null && handleBuy(item.class_level_unlock_id)
            }
            buying={
              purchase.isPending &&
              purchase.variables?.class_level_unlock_id === item.class_level_unlock_id
            }
          />
        ))}
      </CardContent>
    </Card>
  );
}
