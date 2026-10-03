/**
 * BreakthroughsCard (#3045, #4090) — buy a skill's or a language's XP-boundary
 * breakthrough.
 *
 * Reads `GET /api/progression/unlocks/?unlock_type=skill_breakthrough` and
 * `?unlock_type=language_breakthrough` (the same read selectors telnet's
 * `progression unlocks` and the sheet's MechanicsSection `at_boundary` badge
 * draw from) and purchases through `POST /api/progression/unlocks/purchase/` —
 * `PurchaseUnlockAction`, the same seam `progression unlock skill=<id>` /
 * `progression unlock language=<id>` dispatches telnet-side.
 */

import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useProgressionUnlocksQuery, usePurchaseUnlockMutation } from '@/progression/queries';
import type { ProgressionUnlockItem } from '@/progression/types';
import { UnlockItemRow } from './UnlockItemRow';

export function BreakthroughsCard() {
  const skills = useProgressionUnlocksQuery('skill_breakthrough');
  const languages = useProgressionUnlocksQuery('language_breakthrough');
  const purchase = usePurchaseUnlockMutation();

  const isLoading = skills.isLoading || languages.isLoading;
  const error = skills.error ?? languages.error;
  const items = [...(skills.data?.results ?? []), ...(languages.data?.results ?? [])];

  function handleBuy(item: ProgressionUnlockItem) {
    const request =
      item.unlock_type === 'language_breakthrough'
        ? { unlock_type: 'language_breakthrough' as const, language_id: item.language_id }
        : { unlock_type: 'skill_breakthrough' as const, skill_id: item.skill_id };
    purchase.mutate(request, {
      onSuccess: () => toast.success('Breakthrough purchased.'),
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : 'Could not purchase the breakthrough.'),
    });
  }

  return (
    <Card data-testid="breakthroughs-card">
      <CardHeader>
        <CardTitle className="text-base">Breakthroughs</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && (
          <p className="text-sm text-destructive" role="alert">
            Failed to load breakthroughs.
          </p>
        )}
        {!isLoading && !error && items.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="breakthroughs-empty">
            Nothing is parked at a breakthrough right now.
          </p>
        )}
        {items.map((item) => (
          <UnlockItemRow
            key={`${item.unlock_type}-${item.skill_id ?? item.language_id}`}
            item={item}
            onBuy={() => handleBuy(item)}
            buying={
              purchase.isPending &&
              purchase.variables?.unlock_type === item.unlock_type &&
              (purchase.variables?.skill_id ?? purchase.variables?.language_id) ===
                (item.skill_id ?? item.language_id)
            }
          />
        ))}
      </CardContent>
    </Card>
  );
}
