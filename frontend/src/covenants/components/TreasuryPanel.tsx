/**
 * TreasuryPanel — the covenant's shared purse, deposit/withdraw controls (#2992).
 *
 * Hidden entirely when ``treasury_balance`` is null (non-members never see
 * this panel — the server omits the balance from their payload, so there is
 * no "member" prop to thread through separately).
 *
 * Withdraw authority (``treasury.spend_rank_max``) is a server-side rank
 * check — this panel does NOT try to compute it client-side. Both Deposit
 * and Withdraw are always offered to any member; a rank-unauthorized
 * withdrawal surfaces the server's curated ``user_message`` inline rather
 * than being pre-empted in the UI.
 *
 * Mutation goes through the generic action-dispatch endpoint
 * (DepositCovenantFundsAction / WithdrawCovenantFundsAction) — the same seam
 * GroupStoryRequestPanel uses (Decision 8, #2119); mirrors its hook/mutation
 * + queries.ts invalidation pattern.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { formatCoppers } from '@/lib/currency';
import { useDepositCovenantFunds, useWithdrawCovenantFunds } from '@/covenants/queries';

export interface TreasuryPanelProps {
  covenantId: number;
  /** Coppers in the covenant treasury; null when the viewer is not an active member. */
  treasuryBalance: number | null;
  /** ObjectDB pk of the viewer's active character; null if none puppeted. */
  actorCharacterId: number | null;
}

function parsePositiveAmount(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const amount = Number.parseInt(trimmed, 10);
  return amount > 0 ? amount : null;
}

export function TreasuryPanel({
  covenantId,
  treasuryBalance,
  actorCharacterId,
}: TreasuryPanelProps) {
  const [amountText, setAmountText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const deposit = useDepositCovenantFunds(covenantId, actorCharacterId ?? 0);
  const withdraw = useWithdrawCovenantFunds(covenantId, actorCharacterId ?? 0);

  // Non-members never see a balance — nothing to render.
  if (treasuryBalance === null) return null;

  const amount = parsePositiveAmount(amountText);
  const isBusy = deposit.isPending || withdraw.isPending;
  const canAct = amount !== null && actorCharacterId !== null && !isBusy;

  function handleDeposit() {
    if (amount === null || actorCharacterId === null) return;
    setError(null);
    deposit.mutate(amount, {
      onSuccess: () => setAmountText(''),
      onError: (err) =>
        setError(err instanceof Error ? err.message : 'Failed to deposit covenant funds.'),
    });
  }

  function handleWithdraw() {
    if (amount === null || actorCharacterId === null) return;
    setError(null);
    withdraw.mutate(amount, {
      onSuccess: () => setAmountText(''),
      onError: (err) =>
        setError(err instanceof Error ? err.message : 'Failed to withdraw covenant funds.'),
    });
  }

  return (
    <Card data-testid="treasury-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Covenant Treasury</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground" data-testid="treasury-balance">
          {formatCoppers(treasuryBalance)}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={`treasury-amount-${covenantId}`} className="sr-only">
            Amount in coppers
          </label>
          <Input
            id={`treasury-amount-${covenantId}`}
            data-testid="treasury-amount-input"
            inputMode="numeric"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            placeholder="Amount in coppers"
            className="h-8 w-40 text-sm"
          />
          <Button size="sm" onClick={handleDeposit} disabled={!canAct} data-testid="deposit-button">
            {deposit.isPending ? 'Depositing…' : 'Deposit'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleWithdraw}
            disabled={!canAct}
            data-testid="withdraw-button"
          >
            {withdraw.isPending ? 'Withdrawing…' : 'Withdraw'}
          </Button>
        </div>
        {error && (
          <p className="text-sm text-destructive" data-testid="treasury-error">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
