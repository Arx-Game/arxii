/**
 * BreakthroughsCard (#3045) — buy a skill's XP-boundary breakthrough.
 *
 * Reads `GET /api/progression/unlocks/?unlock_type=skill_breakthrough` (the
 * same read selectors telnet's `progression unlocks` and the sheet's
 * MechanicsSection `at_boundary` badge draw from) and purchases through
 * `POST /api/progression/unlocks/purchase/` — `PurchaseUnlockAction`, the
 * same seam `progression unlock skill=<id>` dispatches telnet-side.
 */

import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useProgressionUnlocksQuery, usePurchaseUnlockMutation } from '@/progression/queries';
import { UnlockItemRow } from './UnlockItemRow';

export function BreakthroughsCard() {
  const { data, isLoading, error } = useProgressionUnlocksQuery('skill_breakthrough');
  const purchase = usePurchaseUnlockMutation();

  const items = data?.results ?? [];

  function handleBuy(skillId: number) {
    purchase.mutate(
      { unlock_type: 'skill_breakthrough', skill_id: skillId },
      {
        onSuccess: () => toast.success('Breakthrough purchased.'),
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not purchase the breakthrough.'),
      }
    );
  }

  return (
    <Card data-testid="breakthroughs-card">
      <CardHeader>
        <CardTitle className="text-base">Breakthroughs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Failed to load skill breakthroughs.</p>}
        {!isLoading && !error && items.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="breakthroughs-empty">
            No skills are parked at a breakthrough boundary right now.
          </p>
        )}
        {items.map((item) => (
          <UnlockItemRow
            key={`skill-${item.skill_id}`}
            item={item}
            onBuy={() => item.skill_id !== null && handleBuy(item.skill_id)}
            buying={purchase.isPending && purchase.variables?.skill_id === item.skill_id}
          />
        ))}
      </CardContent>
    </Card>
  );
}
