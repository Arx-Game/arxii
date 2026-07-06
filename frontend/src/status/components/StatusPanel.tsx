/**
 * StatusPanel — qualitative status card stack on the game rail's Status tab (#1446).
 *
 * DESIGN RULING: "The sheet describes; the scene does" — this panel is read-only
 * status; no spend/use buttons for health, stamina (fatigue), or anima, which
 * render as WORDS only (wound description, fatigue zone names, anima band) —
 * never the numeric StatBar used on the character sheet. Coins and Action
 * Points are currencies, so numbers are fine for those two lines.
 *
 * EXCEPTION (#1909): the Withdraw control on the coin line is a deliberate,
 * narrow carve-out — converting ledger coppers into a carriable loose-coin
 * cache is itself a physical-world act (a coin item lands in your hands),
 * not a spend/use ability. The ruling above still holds everywhere else.
 *
 * Mirrors VitalsPanel's null-on-403/404 behavior: when the vitals query yields
 * null (viewer doesn't own this character), the whole panel renders nothing.
 */

import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatCoppers, parseCoppers } from '@/lib/currency';
import { useActionResult } from '@/hooks/actionResultBus';
import type { ActionResultPayload } from '@/hooks/types';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useCharacterAnima, useCharacterResonances } from '@/magic/queries';
import { useCharacterVitalsQuery } from '@/vitals/vitalsQueries';
import type { CharacterStatus } from '@/vitals/vitalsQueries';
import type { MyRosterEntry } from '@/roster/types';
import { useActionPoints, useCharacterPurse } from '../queries';

const STATUS_BADGE_CLASSES: Record<CharacterStatus, string> = {
  alive: 'bg-green-100 text-green-800 border-green-300',
  dying: 'bg-red-100 text-red-800 border-red-300',
  incapacitated: 'bg-amber-100 text-amber-800 border-amber-300',
  dead: 'bg-slate-200 text-slate-700 border-slate-400',
};

const ZONE_BADGE_CLASSES: Record<string, string> = {
  fresh: 'bg-green-100 text-green-800 border-green-300',
  strained: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  tired: 'bg-orange-100 text-orange-800 border-orange-300',
  overexerted: 'bg-red-100 text-red-800 border-red-300',
  exhausted: 'bg-red-200 text-red-900 border-red-400',
};

const FATIGUE_POOL_LABELS = {
  physical: 'Physical',
  social: 'Social',
  mental: 'Mental',
} as const;

interface StatusPanelProps {
  characterId: number;
  /** Active puppet name — required to dispatch Withdraw; the coin line is
   * read-only display without it. */
  characterName?: MyRosterEntry['name'];
}

export function StatusPanel({ characterId, characterName }: StatusPanelProps) {
  const { data: vitals, isLoading } = useCharacterVitalsQuery(characterId);
  const { data: anima } = useCharacterAnima(characterId);
  const { data: resonances = [] } = useCharacterResonances(characterId);
  const { data: purse } = useCharacterPurse(characterId);
  const { data: actionPoints } = useActionPoints(characterId);
  const { executeAction } = useGameSocket();
  const queryClient = useQueryClient();

  const [withdrawText, setWithdrawText] = useState('');

  // Withdraw/deposit/give-coins all land through the websocket action
  // dispatcher — invalidate the purse read on any successful action so the
  // balance stays live without a dedicated per-action payload shape.
  const handleActionResult = useCallback(
    (payload: ActionResultPayload) => {
      if (!payload.success) return;
      queryClient.invalidateQueries({ queryKey: ['status', 'purse', characterId] }).catch(() => {});
    },
    [characterId, queryClient]
  );
  useActionResult(handleActionResult);

  const handleWithdraw = useCallback(() => {
    if (!characterName) return;
    const amount = parseCoppers(withdrawText);
    if (amount == null) return;
    executeAction(characterName, 'withdraw_coins', { amount });
    setWithdrawText('');
  }, [characterName, executeAction, withdrawText]);

  if (isLoading) {
    return (
      <Card data-testid="status-panel-loading">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Status</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (!vitals) return null;

  const animaBand = anima?.band;

  return (
    <Card data-testid="status-panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Status</CardTitle>
          <Badge
            variant="outline"
            className={cn('capitalize', STATUS_BADGE_CLASSES[vitals.status])}
          >
            {vitals.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <section aria-label="Condition" className="space-y-1">
          <p className="text-sm text-muted-foreground">
            {vitals.wound_description || 'A healthy appearance.'}
          </p>
        </section>

        <section aria-label="Fatigue" className="space-y-2">
          <p className="text-sm font-medium">Fatigue</p>
          <div className="flex flex-wrap gap-2">
            {(['physical', 'social', 'mental'] as const).map((pool) => (
              <Badge
                key={pool}
                variant="outline"
                className={cn('text-xs capitalize', ZONE_BADGE_CLASSES[vitals.fatigue[pool].zone])}
              >
                {FATIGUE_POOL_LABELS[pool]}: {vitals.fatigue[pool].zone}
              </Badge>
            ))}
          </div>
        </section>

        {animaBand && (
          <section aria-label="Anima" className="space-y-1">
            <p className="text-sm font-medium">Anima</p>
            <Badge variant="outline" className="text-xs capitalize">
              {animaBand}
            </Badge>
          </section>
        )}

        <section aria-label="Resonances" className="space-y-1">
          <p className="text-sm font-medium">Resonances</p>
          {resonances.length === 0 ? (
            <p className="text-sm text-muted-foreground">No resonances yet.</p>
          ) : (
            <ul className="space-y-0.5 text-sm text-muted-foreground">
              {resonances.map((resonance) => (
                <li key={resonance.id}>{resonance.resonance_name}</li>
              ))}
            </ul>
          )}
        </section>

        <section aria-label="Purse" className="space-y-1.5">
          <p className="text-sm font-medium">Coin</p>
          <p className="text-sm text-muted-foreground">
            {purse ? formatCoppers(purse.balance ?? 0) : 'Unknown.'}
          </p>
          {purse && characterName && (
            <div className="flex items-center gap-1.5">
              <Input
                value={withdrawText}
                onChange={(e) => setWithdrawText(e.target.value)}
                placeholder="1g 2s 3c"
                aria-label="Amount to withdraw"
                className="h-8 text-xs"
              />
              <Button
                size="sm"
                variant="outline"
                onClick={handleWithdraw}
                disabled={parseCoppers(withdrawText) == null}
              >
                Withdraw
              </Button>
            </div>
          )}
        </section>

        <section aria-label="Action Points" className="space-y-1">
          <p className="text-sm font-medium">Action Points</p>
          <p className="text-sm text-muted-foreground">
            {actionPoints ? (
              <>
                {actionPoints.current} of {actionPoints.effective_maximum} this week
                {actionPoints.banked > 0 && ` (+${actionPoints.banked} banked)`}
              </>
            ) : (
              'Unknown.'
            )}
          </p>
        </section>
      </CardContent>
    </Card>
  );
}
