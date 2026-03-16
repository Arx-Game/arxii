/**
 * XP/Kudos page showing account progression data.
 */

import { useState } from 'react';
import { useAccountProgressionQuery, useClaimKudosMutation } from './queries';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import type { KudosClaimCategory, KudosTransaction, XPTransaction } from './types';

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function XPTransactionRow({ transaction }: { transaction: XPTransaction }) {
  const isPositive = transaction.amount > 0;
  return (
    <div className="flex items-center justify-between border-b py-2 last:border-b-0">
      <div className="flex-1">
        <div className="font-medium">{transaction.reason_display}</div>
        <div className="text-sm text-muted-foreground">
          {transaction.description}
          {transaction.character_name && (
            <span className="ml-1">({transaction.character_name})</span>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {formatDate(transaction.transaction_date)}
        </div>
      </div>
      <div className={`text-lg font-bold ${isPositive ? 'text-green-600' : 'text-red-600'}`}>
        {isPositive ? '+' : ''}
        {transaction.amount}
      </div>
    </div>
  );
}

function KudosTransactionRow({ transaction }: { transaction: KudosTransaction }) {
  const isPositive = transaction.amount > 0;
  const categoryName =
    transaction.source_category_name || transaction.claim_category_name || 'Unknown';
  return (
    <div className="flex items-center justify-between border-b py-2 last:border-b-0">
      <div className="flex-1">
        <div className="font-medium">{categoryName}</div>
        <div className="text-sm text-muted-foreground">{transaction.description}</div>
        {transaction.awarded_by_name && (
          <div className="text-xs text-muted-foreground">From: {transaction.awarded_by_name}</div>
        )}
        <div className="text-xs text-muted-foreground">
          {formatDate(transaction.transaction_date)}
        </div>
      </div>
      <div className={`text-lg font-bold ${isPositive ? 'text-green-600' : 'text-amber-600'}`}>
        {isPositive ? '+' : ''}
        {transaction.amount}
      </div>
    </div>
  );
}

function BalanceCard({
  title,
  available,
  earned,
  spent,
  spentLabel = 'Spent',
  action,
}: {
  title: string;
  available: number;
  earned: number;
  spent: number;
  spentLabel?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">{title}</CardTitle>
          {action}
        </div>
      </CardHeader>
      <CardContent>
        <div className="text-4xl font-bold">{available}</div>
        <CardDescription>Available</CardDescription>
        <div className="mt-2 flex gap-4 text-sm text-muted-foreground">
          <div>Earned: {earned}</div>
          <div>
            {spentLabel}: {spent}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ClaimKudosDialog({
  availableKudos,
  claimCategory,
}: {
  availableKudos: number;
  claimCategory: KudosClaimCategory;
}) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [confirming, setConfirming] = useState(false);
  const mutation = useClaimKudosMutation();

  const parsedAmount = parseInt(amount, 10);
  const isValidAmount = !isNaN(parsedAmount) && parsedAmount > 0 && parsedAmount <= availableKudos;
  const xpReward = isValidAmount
    ? Math.floor(parsedAmount / claimCategory.kudos_cost) * claimCategory.reward_amount
    : 0;
  const isConvertible = isValidAmount && xpReward > 0;

  function handleOpenChange(nextOpen: boolean) {
    setOpen(nextOpen);
    if (!nextOpen) {
      setAmount('');
      setConfirming(false);
      mutation.reset();
    }
  }

  function handleConfirm() {
    mutation.mutate(
      { claimCategoryId: claimCategory.id, amount: parsedAmount },
      {
        onSuccess: () => {
          handleOpenChange(false);
        },
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="outline" size="sm" disabled={availableKudos <= 0}>
          Convert to XP
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Convert Kudos to XP</DialogTitle>
          <DialogDescription>
            You have <span className="font-semibold text-foreground">{availableKudos}</span> kudos
            available.
          </DialogDescription>
        </DialogHeader>

        {!confirming ? (
          <>
            <div className="space-y-3 py-2">
              <div className="space-y-1">
                <Label htmlFor="kudos-amount">Amount to convert</Label>
                <div className="flex gap-2">
                  <Input
                    id="kudos-amount"
                    type="number"
                    min={1}
                    max={availableKudos}
                    value={amount}
                    onChange={(e) => setAmount(e.target.value)}
                    placeholder="Enter amount"
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() => setAmount(String(availableKudos))}
                  >
                    Max
                  </Button>
                </div>
              </div>

              {isValidAmount && (
                <p className="text-sm text-muted-foreground">
                  {parsedAmount} kudos <span className="mx-1 text-muted-foreground/50">&rarr;</span>{' '}
                  <span className="font-semibold text-foreground">{xpReward} XP</span>
                </p>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button disabled={!isConvertible} onClick={() => setConfirming(true)}>
                Convert
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <div className="py-2">
              <p className="text-sm">
                Convert{' '}
                <span className="font-semibold">
                  {parsedAmount} kudos to {xpReward} XP
                </span>
                ? This cannot be undone.
              </p>

              {mutation.error && (
                <p className="mt-2 text-sm text-destructive">
                  {mutation.error instanceof Error
                    ? mutation.error.message
                    : 'Something went wrong'}
                </p>
              )}
            </div>

            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setConfirming(false)}
                disabled={mutation.isPending}
              >
                Back
              </Button>
              <Button onClick={handleConfirm} disabled={mutation.isPending}>
                {mutation.isPending ? 'Converting...' : 'Confirm'}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-2">
        <Skeleton className="h-32" />
        <Skeleton className="h-32" />
      </div>
      <Skeleton className="h-64" />
    </div>
  );
}

export function XpKudosPage() {
  const { data, isLoading, error } = useAccountProgressionQuery();

  if (isLoading) {
    return (
      <div className="container mx-auto py-6">
        <h1 className="mb-6 text-2xl font-bold">XP / Kudos</h1>
        <LoadingSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto py-6">
        <h1 className="mb-6 text-2xl font-bold">XP / Kudos</h1>
        <Card>
          <CardContent className="py-8">
            <div className="text-center text-destructive">
              Failed to load progression data. Please try again later.
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const xp = data?.xp;
  const kudos = data?.kudos;
  const xpTransactions = data?.xp_transactions || [];
  const kudosTransactions = data?.kudos_transactions || [];
  // Use the first active claim category — currently only XP conversion exists.
  // If multiple categories are added later, this should become a selector.
  const xpClaimCategory = data?.claim_categories?.[0];

  return (
    <div className="container mx-auto py-6">
      <h1 className="mb-6 text-2xl font-bold">XP / Kudos</h1>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <BalanceCard
          title="Experience Points"
          available={xp?.current_available || 0}
          earned={xp?.total_earned || 0}
          spent={xp?.total_spent || 0}
        />
        <BalanceCard
          title="Kudos"
          available={kudos?.current_available || 0}
          earned={kudos?.total_earned || 0}
          spent={kudos?.total_claimed || 0}
          spentLabel="Claimed"
          action={
            xpClaimCategory && (
              <ClaimKudosDialog
                availableKudos={kudos?.current_available || 0}
                claimCategory={xpClaimCategory}
              />
            )
          }
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Transaction History</CardTitle>
          <CardDescription>Your recent XP and Kudos activity</CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs defaultValue="kudos">
            <TabsList className="mb-4">
              <TabsTrigger value="kudos">Kudos ({kudosTransactions.length})</TabsTrigger>
              <TabsTrigger value="xp">XP ({xpTransactions.length})</TabsTrigger>
            </TabsList>
            <TabsContent value="kudos">
              {kudosTransactions.length > 0 ? (
                <div className="max-h-96 overflow-y-auto">
                  {kudosTransactions.map((t) => (
                    <KudosTransactionRow key={t.id} transaction={t} />
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">
                  No kudos transactions yet
                </div>
              )}
            </TabsContent>
            <TabsContent value="xp">
              {xpTransactions.length > 0 ? (
                <div className="max-h-96 overflow-y-auto">
                  {xpTransactions.map((t) => (
                    <XPTransactionRow key={t.id} transaction={t} />
                  ))}
                </div>
              ) : (
                <div className="py-8 text-center text-muted-foreground">No XP transactions yet</div>
              )}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
